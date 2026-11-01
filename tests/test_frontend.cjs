/* Optional DOM interaction tests. Requires jsdom for testing only, not for Dobara.
   API responses are mocked; this does not test real model accuracy or visual layout. */
const { JSDOM, VirtualConsole } = require(process.env.DOBARA_JSDOM_MODULE || 'jsdom');
const fs = require('fs');
const path = require('path');
const assert = require('assert');
const html = fs.readFileSync(path.join(__dirname, '..', 'static', 'index.html'), 'utf8');
const clone = value => JSON.parse(JSON.stringify(value));
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const all = 'Applications are open to all undergraduate students.';
const finalYear = 'Applications are open only to final-year undergraduate students.';
let records = [], counter = 0, modelCalls = 0, downloadedReport = null, prints = 0;
let failModel = false, failReview = false, failLoad = false, failDelete = false;
let loadDelay = 0, deleteDelay = 0, listDelayOnce = 0;
const errors = [];
const vc = new VirtualConsole();
vc.on('jsdomError', error => errors.push(error.message));
const dom = new JSDOM(html, {
  url: 'http://127.0.0.1:8000/', runScripts: 'dangerously', virtualConsole: vc,
  beforeParse(w) {
    w.Element.prototype.scrollIntoView = function () {};
    w.HTMLAnchorElement.prototype.click = function () {};
    w.confirm = () => true;
    w.Blob = class { constructor(parts) { this.text = parts.join(''); } };
    w.URL.createObjectURL = blob => { downloadedReport = JSON.parse(blob.text); return 'blob:test'; };
    w.URL.revokeObjectURL = () => {};
    w.print = () => { prints++; };
    w.fetch = async (url, options = {}) => {
      const response = (data, status = 200) => ({ ok: status < 400, status, json: async () => clone(data) });
      if (url === '/health') return response({ app: 'Dobara', version: '0.3.1' });
      if (url === '/comparisons') {
        const snapshot = [...records].reverse().map(r => ({
          id: r.id, title: r.result.title, claim: r.input.claim,
          verdict: r.result.verdict, saved_at: r.result.saved.saved_at,
          parent_id: r.result.saved.parent_id,
          review_decision: r.result.review?.decision || 'not_reviewed'
        }));
        const delay = listDelayOnce; listDelayOnce = 0;
        if (delay) await pause(delay);
        return response({ comparisons: snapshot });
      }
      if (url.startsWith('/comparisons/')) {
        const parts = url.split('/'), id = parts[2];
        const record = records.find(r => r.id === id);
        if (parts[3] === 'review') {
          await pause(15);
          if (failReview) return response({ detail: 'Review save failed.' }, 500);
          if (!record) return response({ detail: 'Saved comparison not found.' }, 404);
          const input = JSON.parse(options.body);
          record.result.review = { ...input, updated_at: '2026-11-01T06:00:00.000001+00:00' };
          return response({ comparison_id: id, review: record.result.review });
        }
        if (options.method === 'DELETE') {
          if (deleteDelay) await pause(deleteDelay);
          if (failDelete) return response({ detail: 'Delete failed.' }, 500);
          records = records.filter(r => r.id !== id);
          for (const child of records) if (child.result.saved.parent_id === id) child.result.saved.parent_id = null;
          return response({ deleted: id });
        }
        const snapshot = record ? clone(record) : null;
        if (loadDelay) await pause(loadDelay);
        if (failLoad) return response({ detail: 'Load failed.' }, 500);
        return snapshot ? response(snapshot) : response({ detail: 'Saved comparison not found.' }, 404);
      }
      assert.equal(url, '/analyze'); modelCalls++;
      const input = JSON.parse(options.body); await pause(20);
      if (failModel) return response({ detail: 'Cannot communicate with Ollama.' }, 503);
      const status = source => source.includes('only') ? 'contradicted' : 'supported';
      const earlier = status(input.earlier_source), current = status(input.current_source);
      const result = {
        claim: input.claim,
        verdict: earlier !== 'supported' ? 'baseline_not_supported' : current === 'supported' ? 'still_supported' : 'contradicted',
        analysis: {
          earlier: { status: earlier, reason: 'Mock reason.', evidence: [{ id: 'E1', quote: input.earlier_source }] },
          current: { status: current, reason: 'Mock reason.', evidence: [{ id: 'C1', quote: input.current_source }] }
        },
        model: 'qwen3:4b', elapsed_seconds: 1, evidence_references_valid: true,
        title: input.title || null, source_url: input.source_url || null,
        saved: null, review: null,
        diff: { segments: [{ op: 'equal', text: input.earlier_source }], summary: { changed: false, added_words: 0, removed_words: 0 } }
      };
      if (input.save) {
        result.saved = { id: String(++counter).padStart(32, '0'), parent_id: input.parent_id || null, saved_at: '2026-11-01T05:00:00+00:00' };
        result.review = { decision: 'not_reviewed', note: '', updated_at: null };
        records.push(clone({ id: result.saved.id, input: { claim: input.claim, earlier_source: input.earlier_source, current_source: input.current_source }, result }));
      }
      return response(result);
    };
  }
});
const w = dom.window, d = w.document, el = id => d.getElementById(id);
async function idle() {
  for (let i = 0; i < 200 && el('submit').disabled; i++) await pause(5);
  assert(!el('submit').disabled, 'Controls must be restored');
  await pause(5);
}
async function submit() {
  el('comparison').dispatchEvent(new w.Event('submit', { bubbles: true, cancelable: true }));
  assert(el('submit').disabled); await idle();
}
function clickSample(name) { d.querySelector(`[data-sample=${name}]`).click(); }
function editReview(note, decision = 'revise_claim') {
  el('review-decision').value = decision;
  el('review-decision').dispatchEvent(new w.Event('change'));
  el('review-note').value = note;
  el('review-note').dispatchEvent(new w.Event('input'));
}
(async () => {
  await pause(10); assert(!el('save').checked);
  clickSample('unchanged'); await submit();
  assert.equal(records.length, 0); assert(el('review-controls').hidden);
  el('save').checked = true; el('title').value = 'Saved baseline'; await submit();
  assert.equal(records.length, 1); assert(!el('review-controls').hidden);
  const initial = clone(records[0]);
  editReview('Only final-year students can apply.');
  el('export').click(); assert.equal(downloadedReport.reviewer_review.decision, 'not_reviewed');
  const count = modelCalls;
  el('save-review').click(); assert(el('submit').disabled); await idle();
  assert.equal(modelCalls, count); assert.equal(records[0].result.review.decision, 'revise_claim');
  assert.equal(records[0].input.current_source, initial.input.current_source);
  assert.deepEqual(records[0].result.analysis, initial.result.analysis);
  el('export').click(); assert.equal(downloadedReport.reviewer_review.note, 'Only final-year students can apply.');
  el('print').click(); assert.equal(prints, 1); assert(el('print-report').textContent.includes('Human reviewer decision and note'));
  assert(el('print-report').textContent.includes('Only final-year students can apply.'));
  failReview = true; editReview('Do not lose this draft.'); el('save-review').click(); await idle();
  assert.equal(el('review-note').value, 'Do not lose this draft.'); assert(!el('review-error').hidden);
  assert.equal(records[0].result.review.note, 'Only final-year students can apply.'); failReview = false;
  // A delayed load locks form editing, samples, deletion and inference submission.
  loadDelay = 80; d.querySelector('#history-list li button').click();
  assert(el('submit').disabled); assert(el('claim').readOnly);
  const oldClaim = el('claim').value; clickSample('baseline'); assert.equal(el('claim').value, oldClaim);
  el('comparison').dispatchEvent(new w.Event('submit', { cancelable: true, bubbles: true }));
  assert.equal(modelCalls, count); await idle();
  assert.equal(el('review-note').value, 'Only final-year students can apply.');
  failLoad = true; d.querySelector('#history-list li button').click(); await idle();
  assert(!el('error').hidden); assert(el('result').hidden); failLoad = false;
  d.querySelector('#history-list li button').click(); await idle(); loadDelay = 0;
  el('recheck').click(); assert.equal(el('earlier').value, all); assert.equal(el('current').value, '');
  el('current').value = finalYear; await submit();
  assert.equal(records.length, 2); assert.equal(records[1].result.saved.parent_id, records[0].id);
  assert.equal(records[1].result.review.decision, 'not_reviewed');
  editReview('<img src=x onerror="window.injected=true">', 'find_more_evidence');
  el('save-review').click(); await idle(); el('print').click();
  assert(el('print-report').textContent.includes('<img')); assert.equal(d.querySelectorAll('#print-report img').length, 0); assert.equal(w.injected, undefined);
  // An older history response must not replace a newer one.
  listDelayOnce = 80; el('refresh-history').click();
  const extra = clone(records[0]); extra.id = 'z'.repeat(32); extra.result.saved.id = extra.id; extra.result.title = 'Newer list item'; records.push(extra);
  el('refresh-history').click(); await pause(100);
  assert.equal(d.querySelectorAll('#history-list li').length, 3);
  deleteDelay = 60; failDelete = true; d.querySelector('#history-list li button:nth-child(2)').click();
  assert(el('submit').disabled); await idle(); assert(!el('error').hidden); failDelete = false;
  d.querySelector('#history-list li button:nth-child(2)').click(); await idle(); assert.equal(records.length, 2);
  failModel = true; const draft = el('current').value; await submit();
  assert(!el('error').hidden); assert.equal(el('current').value, draft); failModel = false;
  assert.deepEqual(errors, []);
  console.log('PASS: DOM interactions for saved review, export, print report content, no-inference updates, draft recovery, delayed-load locking, stale history response suppression, recheck, deletion and safe text rendering. API replies mocked; no visual layout or real-model inference tested.');
  dom.window.close();
})().catch(error => { console.error(error); dom.window.close(); process.exit(1); });
