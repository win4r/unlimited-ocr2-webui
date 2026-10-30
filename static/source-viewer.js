/* Continuous original-page reader. Page geometry stays stable while images unload. */
(function (global) {
  'use strict';

  function sourcePageAt(tops, scrollTop, viewportHeight, scrollHeight) {
    if (!tops.length) return 0;
    if (scrollHeight > viewportHeight + 1 && scrollTop + viewportHeight >= scrollHeight - 2) return tops.length;
    const readingLine = scrollTop + Math.min(90, viewportHeight * .2);
    let lo = 0, hi = tops.length;
    while (lo < hi) {
      const mid = (lo + hi) >>> 1;
      if (tops[mid] <= readingLine) lo = mid + 1;
      else hi = mid;
    }
    return Math.max(1, lo);
  }

  class ContinuousSourceViewer {
    constructor({scroller, stack, empty, onPageChange}) {
      Object.assign(this, {scroller, stack, empty, onPageChange});
      this.items = [];
      this.jobId = '';
      this.active = 0;
      this.frame = 0;
      this.navigationTarget = null;
      this.boxesEnabled = false;
      this.boxesByPage = new Map();
      this.anchor = {page: 1, ratio: 0};
      this.width = scroller.clientWidth;
      this.observer = typeof IntersectionObserver === 'function' ? new IntersectionObserver(records => {
        for (const record of records) {
          const item = this.items[Number(record.target.dataset.page) - 1];
          if (item?.figure === record.target) this.mount(item, record.isIntersecting);
        }
      }, {root: scroller, rootMargin: '800px 0px'}) : null;
      scroller.addEventListener('scroll', () => this.schedule(), {passive: true});
      const userScroll = event => {
        if (event.type === 'keydown' && !['ArrowDown','ArrowUp','PageDown','PageUp','Home','End',' '].includes(event.key)) return;
        this.navigationTarget = null;
        this.schedule();
      };
      for (const type of ['wheel','touchstart','pointerdown','keydown']) scroller.addEventListener(type, userScroll, {passive: true});
      if (typeof ResizeObserver === 'function') {
        this.resize = new ResizeObserver(() => {
          const width = scroller.clientWidth;
          if (width !== this.width && this.items.length) {
            const item = this.items[this.anchor.page - 1];
            if (item) {
              this.navigationTarget = this.anchor.page;
              scroller.scrollTop = this.top(item) + this.anchor.ratio * item.figure.offsetHeight;
            }
          }
          this.width = width;
          this.schedule();
        });
        this.resize.observe(scroller);
      }
    }

    clear() {
      if (this.frame) cancelAnimationFrame(this.frame);
      this.frame = 0;
      this.observer?.disconnect();
      this.items = [];
      this.jobId = '';
      this.active = 0;
      this.navigationTarget = null;
      this.anchor = {page: 1, ratio: 0};
      this.boxesByPage.clear();
      this.boxesEnabled = false;
      this.stack.replaceChildren();
      this.stack.classList.add('hidden');
      this.empty.classList.remove('hidden');
      this.scroller.scrollTop = 0;
    }

    setDocument(id, pages) {
      if (id === this.jobId && pages.length === this.items.length) return;
      if (id !== this.jobId || pages.length < this.items.length) this.clear();
      this.jobId = id;
      for (const entry of pages.slice(this.items.length)) {
        const number = this.items.length + 1;
        const figure = document.createElement('figure');
        figure.className = 'source-page';
        figure.dataset.page = String(number);
        figure.setAttribute('aria-label', `原始文档第 ${number} 页`);
        const caption = document.createElement('figcaption');
        caption.className = 'source-page-caption';
        caption.textContent = `第 ${number} 页 · ${entry.source} · 原文件第 ${entry.source_page} 页`;
        const sheet = document.createElement('div');
        sheet.className = 'source-page-image';
        const width = Math.max(1, Number(entry.width) || 595), height = Math.max(1, Number(entry.height) || 842);
        sheet.style.aspectRatio = `${width} / ${height}`;
        const image = document.createElement('img');
        image.width = width;
        image.height = height;
        image.alt = `文档第 ${number} 页`;
        image.decoding = 'async';
        image.draggable = false;
        const overlay = document.createElement('div');
        overlay.className = 'source-boxes';
        overlay.setAttribute('aria-hidden', 'true');
        sheet.append(image, overlay);
        figure.append(caption, sheet);
        this.stack.append(figure);
        const item = {number, figure, image, overlay, url: `/api/jobs/${id}/pages/${number}`};
        this.items.push(item);
        if (this.observer) this.observer.observe(figure);
        else this.mount(item, true);
      }
      this.stack.classList.toggle('hidden', !this.items.length);
      this.empty.classList.toggle('hidden', !!this.items.length);
      if (!this.active && this.items.length) this.activate(1);
      this.schedule();
    }

    top(item) { return this.stack.offsetTop + item.figure.offsetTop; }

    goTo(number) {
      if (!this.items.length) return;
      number = Math.max(1, Math.min(this.items.length, Math.round(Number(number) || 1)));
      this.navigationTarget = number;
      this.activate(number);
      this.scroller.scrollTop = this.top(this.items[number - 1]);
      this.schedule();
    }

    activate(number) {
      if (number === this.active) return;
      this.items[this.active - 1]?.figure.classList.remove('is-current');
      this.active = number;
      this.items[number - 1]?.figure.classList.add('is-current');
      this.onPageChange(number);
    }

    schedule() {
      if (this.frame) return;
      this.frame = requestAnimationFrame(() => {
        this.frame = 0;
        if (!this.items.length) return;
        const n = this.navigationTarget ?? sourcePageAt(this.items.map(item => this.top(item)), this.scroller.scrollTop, this.scroller.clientHeight, this.scroller.scrollHeight);
        this.activate(n);
        const item = this.items[n - 1];
        this.anchor = {page: n, ratio: (this.scroller.scrollTop - this.top(item)) / Math.max(1, item.figure.offsetHeight)};
      });
    }

    mount(item, visible) {
      if (visible) {
        if (!item.image.hasAttribute('src')) item.image.src = item.url;
        this.drawOverlay(item);
      } else {
        item.image.removeAttribute('src');
        item.overlay.replaceChildren();
      }
    }

    setBoxes(blocks, enabled) {
      this.boxesEnabled = enabled;
      this.boxesByPage.clear();
      for (const block of blocks) {
        const list = this.boxesByPage.get(block.page) || [];
        list.push(block);
        this.boxesByPage.set(block.page, list);
      }
      for (const item of this.items) this.drawOverlay(item);
    }

    drawOverlay(item) {
      item.overlay.replaceChildren();
      if (!this.boxesEnabled || !item.image.hasAttribute('src')) return;
      for (const block of this.boxesByPage.get(item.number) || []) {
        if (!block.bbox) continue;
        const [x1,y1,x2,y2] = block.bbox;
        if (x2 <= x1 || y2 <= y1) continue;
        const box = document.createElement('div');
        box.className = 'bbox';
        Object.assign(box.style, {left:x1/10+'%',top:y1/10+'%',width:(x2-x1)/10+'%',height:(y2-y1)/10+'%'});
        const label = document.createElement('span');
        label.textContent = block.label;
        box.append(label);
        item.overlay.append(box);
      }
    }
  }

  if (global) global.ContinuousSourceViewer = ContinuousSourceViewer;
  if (typeof module !== 'undefined' && module.exports) module.exports = {sourcePageAt};
})(typeof window !== 'undefined' ? window : null);
