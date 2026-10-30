/* Recording tools: all measurements come from the server; no simulated meters. */
const studio = {resourceBusy:false, pageBusy:false, pageResult:null, scope:'document',
  compareTarget:'', compareKey:'', comparison:null, textBusy:false, lastTextKey:''};

document.querySelector('header').insertAdjacentHTML('beforeend', `
  <div class="header-actions"><button id="record-mode" aria-pressed="false">录屏模式</button>
  <a class="button" href="/api/metrics.csv">导出实测总表</a></div>`);
document.querySelector('.main').insertAdjacentHTML('afterbegin', `
<section class="card resource-card" id="resource-panel">
  <div class="resource-heading"><div><strong>服务器实时资源</strong><span class="sub" id="resource-status">正在连接采样器</span></div>
  <select id="trace-scope" aria-label="资源曲线范围"><option value="task">所选任务曲线</option><option value="live">服务器实时曲线</option></select></div>
  <div class="resource-grid">
    <div><div class="resource-label">GPU 计算利用率</div><div class="resource-value" id="gpu-util">—</div><div class="resource-bar"><i id="gpu-util-bar"></i></div><div class="resource-detail" id="gpu-util-peak">等待采样</div></div>
    <div><div class="resource-label">整卡显存</div><div class="resource-value" id="gpu-vram">—</div><div class="resource-bar"><i id="gpu-vram-bar"></i></div><div class="resource-detail" id="gpu-vram-peak">包含服务预留的显存池</div></div>
    <div><div class="resource-label">系统 RAM 占用</div><div class="resource-value" id="host-ram">—</div><div class="resource-bar ram-bar"><i id="ram-bar"></i></div><div class="resource-detail" id="ram-peak">按总量 − 可用内存计算</div></div>
    <div><div class="resource-label">CPU 总利用率</div><div class="resource-value" id="host-cpu">—</div><div class="resource-bar cpu-bar"><i id="cpu-bar"></i></div><div class="resource-detail" id="cpu-peak">全机口径，0–100%</div></div>
  </div>
  <div class="resource-charts">
    <div class="chart"><div class="chart-title"><strong>整卡显存 · GiB</strong><span id="vram-range"></span></div><div id="vram-chart"></div></div>
    <div class="chart"><div class="chart-title"><strong>系统 RAM · GiB</strong><span id="ram-range"></span></div><div id="ram-chart"></div></div>
    <div class="chart"><div class="chart-title"><strong>利用率 · GPU 蓝 / CPU 橙</strong><span id="util-range"></span></div><div id="util-chart"></div></div>
  </div>
  <div class="resource-method"><span id="resource-extra">每秒独立采样，浏览器刷新不会重置记录</span><details><summary>测量口径</summary>
  <p>上方数字是服务器当前值，曲线可切换为所选任务的历史记录。显存采用整卡已用值，包含 SGLang 预留池和其他进程；系统 RAM 按总内存减可用内存计算。任务峰值来自 1 秒采样，可能漏掉更短的瞬时峰值，不等于模型单独占用、KV 缓存大小或 CUDA 分配器的精确峰值。图表纵轴从 0 开始，最多显示最近 180 个采样点，下载 CSV 可获得完整记录。字符数与字符流速按原始输出统计，包含布局标记；tokens 采用模型服务实际上报值。长文档可能仅在结束时上报汇总 tokens，期间不伪造 token 数。</p></details></div>
</section>`);
document.querySelector('.options').insertAdjacentHTML('afterend', `
  <div class="run-notes"><label for="run-notes">测试备注</label><input type="text" id="run-notes" maxlength="240" placeholder="例如：中文财报 / 已预热 / 300 DPI；会随实测结果保存"></div>`);
$('stats').insertAdjacentHTML('beforeend', `
  <div class="stat"><span>任务耗时 · 不含上传/排队</span><strong id="stat-total">—</strong></div>
  <div class="stat"><span>原始输出字符 · 含标记</span><strong id="stat-chars">—</strong></div>`);
document.querySelector('.statusbar').insertAdjacentHTML('beforeend', `
  <div class="studio-tools"><button id="rerun" disabled>同图切换模式重跑</button><span id="stream-rate"></span><span id="timing-note">首 token 与推理请求计时均从服务器发起模型请求时开始</span><span id="studio-message"></span></div>`);
document.querySelector('.result .pane-head .tabs').insertAdjacentHTML('beforebegin', `
  <select class="scope-select" id="result-scope" aria-label="结果查看范围"><option value="document">整篇合并</option><option value="page">跟随当前页</option></select>`);
$('downloads').insertAdjacentHTML('afterbegin', `
  <a class="button hidden" id="resources-download" data-file="resources.csv">资源 CSV</a>
  <a class="button hidden" id="text-check-download" data-file="text-check.json">文字核对 JSON</a>`);
$('workspace').insertAdjacentHTML('afterend', `
<details class="card bench-card" id="compare-panel"><summary>同输入任务对照</summary><div class="bench-content">
  <p class="bench-note">选择一个已完成任务，与当前任务并排比较。用“同图切换模式重跑”可复用完全相同的页面图像，适合演示 Base 与 Gundam 的区别。</p>
  <div class="compare-controls"><select id="compare-select" aria-label="选择对照任务"><option value="">请选择对照任务</option></select><a class="button" href="/api/metrics.csv">下载全部指标 CSV</a></div>
  <div id="comparison"><div class="bench-note">先选择一个解析任务。</div></div></div></details>
<details class="card bench-card" id="text-check-panel"><summary>人工参考文本核对 · CER 辅助评估</summary><div class="bench-content">
  <p class="bench-note">粘贴与所选页或整篇对应的人工校对文本。只比较识别文字；表格转为单元格文字，公式保留 LaTeX。此功能不评价表格结构、版式、公式语义或整个模型的通用准确率。</p>
  <div class="check-grid"><div><label for="reference-text">人工校对参考文本</label><textarea id="reference-text" maxlength="20000" placeholder="请输入真实参考内容，最多 20,000 字符。"></textarea></div>
  <div><label for="recognized-text">所选范围的识别文字（自动提取）</label><textarea id="recognized-text" readonly placeholder="任务完成后显示。"></textarea></div></div>
  <div class="check-controls"><select id="check-scope" aria-label="文字核对范围"><option value="page">当前页</option><option value="document">整篇</option></select>
  <label><input type="checkbox" id="ignore-whitespace" checked>忽略所有空白字符</label><button id="run-text-check" class="primary">计算字符错误率</button><span class="sub" id="check-status"></span></div>
  <div id="check-result"></div></div></details>`);

function numberText(value, digits=1) { return Number.isFinite(value) ? value.toFixed(digits) : '—'; }
function bar(id, value) { $(id).style.width=`${Number.isFinite(value)?Math.max(0,Math.min(100,value)):0}%`; }
function tell(message) { $('studio-message').textContent=message; }

function plot(id, rows, keys, maximum, colors) {
  if (!rows.length) { $(id).innerHTML='<div class="chart-empty">此任务还没有资源采样记录</div>'; return; }
  const width=480,height=100,pad=14,lo=rows[0].elapsed_seconds||0,hi=rows.at(-1).elapsed_seconds||lo+1;
  const x=t=>pad+(t-lo)/Math.max(.001,hi-lo)*(width-pad*2);
  const y=v=>height-pad-Math.max(0,Math.min(maximum,v))/Math.max(1,maximum)*(height-pad*2);
  let svg=`<svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" role="img" aria-label="资源采样曲线"><path d="M${pad},${pad}H${width-pad}M${pad},${height/2}H${width-pad}M${pad},${height-pad}H${width-pad}" stroke="#e7ebf3" fill="none" stroke-width="1"/>`;
  keys.forEach((key,index)=>{
    const points=rows.filter(row=>Number.isFinite(row[key]));
    if(points.length)svg+=`<polyline fill="none" stroke="${colors[index]}" stroke-width="2" vector-effect="non-scaling-stroke" points="${points.map(row=>`${x(row.elapsed_seconds).toFixed(2)},${y(row[key]).toFixed(2)}`).join(' ')}"/>`;
    if(points.length===1)svg+=`<circle cx="${x(points[0].elapsed_seconds)}" cy="${y(points[0][key])}" r="2" fill="${colors[index]}"/>`;
  });
  svg+=`<text x="1" y="12" font-size="10" fill="#8490a4">${numberText(maximum,0)}</text><text x="2" y="95" font-size="10" fill="#8490a4">0</text></svg>`;
  $(id).innerHTML=svg;
}

async function refreshResources() {
  if(studio.resourceBusy)return;studio.resourceBusy=true;
  try {
    const useTask=$('trace-scope').value==='task'&&current;
    const data=await api('/api/resources'+(useTask?'?job_id='+current:''));
    const sample=data.current,gpu=sample.gpu||{},summary=data.job_summary,peaks=summary?.peaks||{};
    $('resource-status').textContent=sample.age_seconds>3?'采样暂时延迟':`1 秒采样 · ${gpu.source||'CPU/RAM'}${useTask?' · 所选任务曲线':' · 实时曲线'}`;
    $('gpu-util').innerHTML=`${numberText(gpu.utilization,0)}<small>%</small>`;
    $('gpu-vram').innerHTML=`${numberText(gpu.used_gib)}<small>/ ${numberText(gpu.total_gib)} GiB</small>`;
    $('host-ram').innerHTML=`${numberText(sample.ram_used_gib)}<small>/ ${numberText(sample.ram_total_gib)} GiB</small>`;
    $('host-cpu').innerHTML=`${numberText(sample.cpu_percent,0)}<small>%</small>`;
    bar('gpu-util-bar',gpu.utilization);bar('gpu-vram-bar',gpu.used_gib/gpu.total_gib*100);
    bar('ram-bar',sample.ram_percent);bar('cpu-bar',sample.cpu_percent);
    $('gpu-util-peak').textContent=summary?`任务采样峰值 ${numberText(peaks.gpu_util_percent,0)}%`:'整卡口径';
    $('gpu-vram-peak').textContent=summary?`任务峰值 ${numberText(peaks.gpu_memory_used_gib,2)} GiB · 较基线 +${numberText(summary.gpu_memory_increase_gib,2)}`:'包含服务预留的显存池';
    $('ram-peak').textContent=summary?`任务峰值 ${numberText(peaks.ram_used_gib,2)} GiB · 较基线 +${numberText(summary.ram_increase_gib,2)}`:`当前可用 ${numberText(sample.ram_available_gib)} GiB`;
    $('cpu-peak').textContent=summary?`任务采样峰值 ${numberText(peaks.cpu_percent,0)}%`:`${sample.cpu_count||'—'} 个逻辑 CPU · 全机口径`;
    const rows=data.history||[];plot('vram-chart',rows,['gpu_memory_used_gib'],gpu.total_gib||48,['#315ce7']);
    plot('ram-chart',rows,['ram_used_gib'],sample.ram_total_gib||100,['#159d7a']);
    plot('util-chart',rows,['gpu_util_percent','cpu_percent'],100,['#315ce7','#d58a25']);
    const range=rows.length?`${numberText(rows[0].elapsed_seconds,0)}–${numberText(rows.at(-1).elapsed_seconds,0)} 秒`:'';
    for(const id of ['vram-range','ram-range','util-range'])$(id).textContent=range;
    $('resource-extra').textContent=`${gpu.name||'GPU 待连接'} · ${numberText(gpu.temperature_c,0)}°C · ${numberText(gpu.power_w,0)} W`+(summary?` · 本任务 ${summary.sample_count} 个记录点 · 峰值为采样值`:' · 新任务会自动记录峰值和完整 CSV');
    $('resources-download').classList.toggle('hidden',!job?.stats.resources?.available);
  } catch(error) { $('resource-status').textContent='资源数据暂时无法更新'; }
  finally { studio.resourceBusy=false; }
}

async function updatePageResult() {
  if(studio.scope!=='page'||!job||!job.pages.length||studio.pageBusy)return;
  const id=current,n=page;studio.pageBusy=true;
  try { const result=await api(`/api/jobs/${id}/page-result/${n}`);if(current===id&&page===n){studio.pageResult=result;lastContent='';renderContent(true);} }
  catch(error) { tell(error.message); }finally{studio.pageBusy=false;if(current!==id||page!==n)updatePageResult();}
}

function comparisonOptions(list) {
  const select=$('compare-select'),selected=studio.compareTarget;
  select.innerHTML='<option value="">请选择对照任务</option>'+list.filter(j=>j.id!==current&&j.status==='completed').map(j=>`<option value="${j.id}">${esc(j.name)} · ${esc(j.options.mode)} · ${new Date(j.created_at).toLocaleTimeString()}</option>`).join('');
  if(Array.from(select.options).some(o=>o.value===selected))select.value=selected;
}

async function refreshComparison(force=false) {
  if(!job||!studio.compareTarget){$('comparison').innerHTML='<div class="bench-note">选择另一个任务，或点击“同图切换模式重跑”。</div>';return;}
  const key=[current,studio.compareTarget,job.status,job.stats.inference_seconds,job.stats.resources?.sample_count].join('|');
  if(!force&&key===studio.compareKey)return;studio.compareKey=key;
  try {
    const result=await api(`/api/compare?left=${studio.compareTarget}&right=${current}`);studio.comparison=result;
    const [left,right]=result.rows;
    const fields=[['解析模式','mode'],['选中页面','pages'],['任务总耗时（不含上传/排队）','total_seconds',' 秒'],['页面准备','preparation_seconds',' 秒'],['推理请求耗时','request_seconds',' 秒'],['首内容 token 等待','time_to_first_token',' 秒'],['输出 tokens','completion_tokens'],['请求综合吞吐','request_tokens_per_second',' tokens/s'],['整卡采样峰值显存','peak_gpu_memory_gib',' GiB'],['较各自任务前显存增量','gpu_memory_increase_gib',' GiB'],['系统 RAM 采样峰值','peak_ram_gib',' GiB'],['计时版本','measurement_version']];
    const value=(row,key,unit='')=>row[key]==null?'未采集':esc(typeof row[key]==='number'?Number.isInteger(row[key])?row[key]:row[key].toFixed(2):row[key])+unit;
    $('comparison').innerHTML=`<div class="same-input ${result.same_input?'':'different-input'}">${result.same_input?'✓ 输入图像 SHA-256 相同':'输入图像不同或历史指纹缺失'}${result.same_input?' · '+esc(left.input_sha256.slice(0,16))+'…':''}</div><table class="compare-table"><thead><tr><th>指标</th><th>${esc(left.name)}</th><th>${esc(right.name)}</th></tr></thead><tbody>${fields.map(([label,key,unit])=>`<tr><td class="metric-name">${label}</td><td>${value(left,key,unit)}</td><td>${value(right,key,unit)}</td></tr>`).join('')}</tbody></table><p class="bench-note">${result.notes.map(esc).join('<br>')}</p>`;
  }catch(error){$('comparison').textContent=error.message;}
}

async function loadRecognizedText() {
  if(!job||job.status!=='completed'){$('recognized-text').value='';return;}
  const n=$('check-scope').value==='page'?page:0,key=`${current}:${n}`;
  if(studio.lastTextKey===key)return;studio.lastTextKey=key;
  try { const result=await api(`/api/jobs/${current}/text?page=${n}`);if(studio.lastTextKey===key)$('recognized-text').value=result.text; }
  catch(error){$('check-status').textContent=error.message;}
}

function showTextCheck(report) {
  const expected=report.diff.map(op=>op.tag==='equal'?esc(op.reference):op.reference?`<del>${esc(op.reference)}</del>`:'').join('');
  const actual=report.diff.map(op=>op.tag==='equal'?esc(op.actual):op.actual?`<ins>${esc(op.actual)}</ins>`:'').join('');
  $('check-result').innerHTML=`<div class="check-summary"><div>CER 字符错误率<br><strong>${report.character_error_percent.toFixed(2)}%</strong></div><div>参考字符 ${report.reference_characters}<br>替换 ${report.substitutions} · 删除 ${report.deletions} · 插入 ${report.insertions}</div><div>范围：${report.page?'第 '+report.page+' 页':'整篇'}<br>${report.normalization==='remove_all_whitespace'?'已忽略空白，保留标点和大小写':'逐 Unicode 字符严格比较'}</div></div><div class="diff-grid"><div><div class="diff-caption">参考文本 · 红色为差异</div><div class="diff-box">${expected}</div></div><div><div class="diff-caption">识别文本 · 绿色为差异</div><div class="diff-box">${actual}</div></div></div><p class="bench-note">CER =（替换 + 删除 + 插入）÷ 参考字符数，越低越好，可能超过 100%。这不是整模型准确率，也不评价表格结构与公式语义。核对报告已加入本任务 ZIP。</p>`;
}

window.labHooks={
  jobs(list){comparisonOptions(list);},
  selected(id){studio.pageResult=null;studio.lastTextKey='';studio.compareKey='';studio.compareTarget='';$('comparison').innerHTML='';$('reference-text').value='';$('recognized-text').value='';$('check-result').innerHTML='';$('check-status').textContent='';tell('');history.replaceState({},'',location.pathname+'?job='+id);refreshResources();},
  reset(){studio.pageResult=null;studio.compareTarget='';studio.compareKey='';$('check-result').innerHTML='';$('reference-text').value='';$('recognized-text').value='';$('comparison').innerHTML='';$('rerun').disabled=true;$('run-text-check').disabled=true;$('stream-rate').textContent='';history.replaceState({},'',location.pathname);refreshResources();},
  job(value){
    const s=value.stats,active=['queued','running'].includes(value.status),speed=$('stat-speed');
    $('stat-total').textContent=numberText(value.elapsed,1)+' 秒';$('stat-chars').textContent=(s.output_characters??value.raw.length).toLocaleString();
    $('stat-tokens').textContent=s.completion_tokens!=null?s.completion_tokens.toLocaleString():'待服务上报';
    speed.previousElementSibling.textContent='请求综合吞吐 · tokens/s';
    speed.textContent=active?(s.completion_tokens!=null&&s.request_elapsed_seconds>0?numberText(s.completion_tokens/s.request_elapsed_seconds,2):'待服务上报'):numberText(s.tokens_per_second,2);
    $('stream-rate').textContent=s.live_characters_per_second!=null?`${active?'近约 3 秒流速':'末段观测流速'} ${numberText(s.live_characters_per_second,1)} 原始字符/s`:'';
    $('stat-first').previousElementSibling.textContent='首内容 token 等待 · 秒';$('stat-first').textContent=numberText(s.time_to_first_token,2);
    $('stat-pages').previousElementSibling.textContent='输入页数 / 已结束输出';$('stat-pages').textContent=`${value.pages.length} / ${s.ended_pages??(value.status==='completed'?value.pages.length:Math.max(0,(s.output_page_markers||0)-1))}`;
    $('rerun').disabled=active||!value.pages.length;$('rerun').textContent=active?'任务完成后可同图重跑':value.status==='completed'?'同图重跑 '+(value.options.mode==='gundam'?'Base':'Gundam'):'使用原模式恢复';
    $('run-text-check').disabled=value.status!=='completed';
    $('resources-download').classList.toggle('hidden',!s.resources?.available);$('text-check-download').classList.toggle('hidden',!s.text_check);
    $('timing-note').textContent=`${value.options.mode==='gundam'?'Gundam 清晰细节':'Base 全局视图'} · ${value.options.dpi} DPI · ${value.options.tokens_per_page} tokens/页`+(s.preparation_seconds!=null?` · 准备 ${s.preparation_seconds.toFixed(2)}s`:'')+(s.request_elapsed_seconds!=null?` · 请求 ${s.request_elapsed_seconds.toFixed(2)}s`:'')+(value.options.reused_prepared_pages?' · 复用相同页面图像':'');
    if(value.options.parent_job_id&&!studio.compareTarget){studio.compareTarget=value.options.parent_job_id;comparisonOptions(allJobs);$('compare-panel').open=true;}
    if(studio.compareTarget)refreshComparison();if(studio.scope==='page')updatePageResult();
    if($('text-check-panel').open)loadRecognizedText();
  },
  content(value,selectedTab){if(studio.scope!=='page'||selectedTab==='logs')return null;const result=studio.pageResult;if(!result||result.page!==page)return '';return selectedTab==='preview'?result.rendered:selectedTab==='markdown'?result.markdown:result.raw;},
  page(){studio.pageResult=null;studio.lastTextKey='';if(studio.scope==='page'){firstResult=true;lastContent='';renderContent(true);updatePageResult();}if($('check-scope').value==='page'){$('check-result').innerHTML='';$('check-status').textContent=$('reference-text').value.trim()?`已切换到第 ${page} 页，请确认参考文本对应当前页。`:'';}if($('text-check-panel').open)loadRecognizedText();}
};

$('record-mode').onclick=()=>{const enabled=document.body.classList.toggle('recording');$('record-mode').textContent=enabled?'退出录屏':'录屏模式';$('record-mode').setAttribute('aria-pressed',String(enabled));localStorage.setItem('uocr-recording',enabled?'1':'0');};
document.addEventListener('keydown',event=>{if(event.key==='Escape'&&document.body.classList.contains('recording'))$('record-mode').click();});
if(localStorage.getItem('uocr-recording')==='1')$('record-mode').click();
$('trace-scope').onchange=refreshResources;
$('result-scope').onchange=()=>{studio.scope=$('result-scope').value;studio.pageResult=null;firstResult=true;lastContent='';renderContent(true);updatePageResult();};
$('compare-select').onchange=()=>{studio.compareTarget=$('compare-select').value;refreshComparison(true);};
$('check-scope').onchange=()=>{studio.lastTextKey='';loadRecognizedText();};
$('text-check-panel').ontoggle=()=>{if($('text-check-panel').open)loadRecognizedText();};
$('rerun').onclick=async()=>{if(!job)return;const parent=current;try{$('rerun').disabled=true;tell('正在复制相同页面图像…');const form=new FormData();if(job.status!=='completed')form.append('mode',job.options.mode);const result=await api(`/api/jobs/${parent}/rerun`,{method:'POST',body:form});await selectJob(result.id);refreshJobs();}catch(error){tell(error.message);$('rerun').disabled=false;}};
$('run-text-check').onclick=async()=>{if(!job)return;const form=new FormData();form.append('reference',$('reference-text').value);form.append('page',$('check-scope').value==='page'?page:0);form.append('ignore_whitespace',$('ignore-whitespace').checked?'true':'false');$('run-text-check').disabled=true;$('check-status').textContent='正在核对…';try{const report=await api(`/api/jobs/${current}/text-check`,{method:'POST',body:form});showTextCheck(report);$('check-status').textContent='报告已保存';await refreshCurrent();}catch(error){$('check-status').textContent=error.message;}finally{$('run-text-check').disabled=false;}};

comparisonOptions(allJobs);refreshResources();setInterval(refreshResources,1000);
const initialJob=new URLSearchParams(location.search).get('job');
if(initialJob&&/^[a-f0-9]{32}$/.test(initialJob))selectJob(initialJob);
