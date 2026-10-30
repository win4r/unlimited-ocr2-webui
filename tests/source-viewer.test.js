const test = require('node:test');
const assert = require('node:assert/strict');
const {sourcePageAt} = require('../static/source-viewer.js');

test('empty and single-page documents keep valid page numbers', () => {
  assert.equal(sourcePageAt([], 0, 600, 600), 0);
  assert.equal(sourcePageAt([14], 700, 600, 1300), 1);
});
test('scrolling forward and backward crosses page boundaries', () => {
  const tops = [14, 1014, 2014];
  assert.equal(sourcePageAt(tops, 0, 600, 3014), 1);
  assert.equal(sourcePageAt(tops, 950, 600, 3014), 2);
  assert.equal(sourcePageAt(tops, 850, 600, 3014), 1);
});
test('a short final landscape page is selected at the bottom', () => {
  assert.equal(sourcePageAt([14, 1200, 2500], 2000, 600, 2600), 3);
});
test('a document fitting inside the viewport starts on page one', () => {
  assert.equal(sourcePageAt([14, 200, 400], 0, 800, 650), 1);
});
test('mixed page heights and a 300-page document retain ordered indices', () => {
  assert.equal(sourcePageAt([14, 500, 1800], 470, 600, 2800), 2);
  const tops = Array.from({length:300}, (_, i) => 14 + i * 842);
  assert.equal(sourcePageAt(tops, tops[159], 600, 252614), 160);
  assert.equal(sourcePageAt(tops, 252014, 600, 252614), 300);
});
