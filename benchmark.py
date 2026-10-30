"""Transparent text checks and input fingerprints for recording comparisons."""
import hashlib
from html.parser import HTMLParser
import re

from rapidfuzz.distance import Levenshtein
from vendor.process_unlimitedOCR2 import _parse_blocks, STRAY_TOKEN_RE

MODEL_REVISION = "c14071b549f4fcab10909f3c4acc6a2edb366947"
MEASUREMENT_VERSION = "video-v2"


def input_fingerprint(paths):
    digest = hashlib.sha256()
    for path in paths:
        data = path.read_bytes()
        digest.update(len(data).to_bytes(8,"big"))
        digest.update(data)
    return digest.hexdigest()


class _TableText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts=[]

    def handle_data(self, data):
        self.parts.append(data)


def extracted_text(raw, page=0):
    output=[]
    for block in _parse_blocks(raw):
        if page and block["page"] != page:
            continue
        label=re.sub(r"^(?:cross_|append_)","",block["label"])
        if label in ("image","figure","picture","chart","img","seal"):
            continue
        content=STRAY_TOKEN_RE.sub("", block["content"])
        if "table" in label:
            parser=_TableText();parser.feed(content);content=" ".join(parser.parts)
        output.append(content.strip())
    return "\n\n".join(x for x in output if x)


def compare_text(reference, hypothesis, ignore_whitespace=True):
    if len(reference)>20000 or len(hypothesis)>20000:
        raise ValueError("单次文字核对最多 20,000 字符；长文档请按页核对。")
    normalize=lambda s:re.sub(r"\s+","",s) if ignore_whitespace else s
    expected, actual=normalize(reference),normalize(hypothesis)
    if not expected:
        raise ValueError("请输入非空的人工校对参考文本。")
    distance=Levenshtein.distance(expected,actual)
    counts={"insert":0,"delete":0,"replace":0}
    for op in Levenshtein.editops(expected,actual):
        counts[op.tag]+=1
    diff=[dict(tag=tag,reference=expected[i:j],actual=actual[k:l])
          for tag,i,j,k,l in Levenshtein.opcodes(expected,actual)]
    return dict(character_error_rate=distance/len(expected), character_error_percent=round(distance/len(expected)*100,4),
                edit_distance=distance,reference_characters=len(expected),output_characters=len(actual),
                substitutions=counts["replace"],deletions=counts["delete"],insertions=counts["insert"],
                normalization="remove_all_whitespace" if ignore_whitespace else "exact_unicode_characters",
                formula="CER = (substitutions + deletions + insertions) / reference characters",
                limitation="Only this reference text is checked. This does not score layout, table structure, formula semantics or whole-model OCR accuracy. CER may exceed 100%.",
                reference=reference,hypothesis=hypothesis,diff=diff)


def csv_safe(value):
    if isinstance(value,str) and (value.startswith(("\t","\r","\n")) or value.lstrip().startswith(("=","+","-","@"))):
        return "'"+value
    return value
