// lighthouse-audit.mjs — compact performance audit for Claude Code
// Usage: node scripts/lighthouse-audit.mjs [url]
// Default URL: http://localhost:3000
import { execSync } from 'child_process';
import { readFileSync, unlinkSync } from 'fs';

const args = process.argv.slice(2);
const full = args.includes('--full');
const url = args.find(a => !a.startsWith('--')) || 'http://localhost:3000';
const tmpFile = '/tmp/lh-report.json';

console.log(`Running Lighthouse on ${url}...\n`);

try {
  execSync(
    `lighthouse ${url} --output=json --output-path=${tmpFile} --chrome-flags="--headless --no-sandbox" --quiet`,
    { stdio: 'inherit' }
  );
} catch (e) {
  console.error('Lighthouse failed. Is it installed? npm install -g lighthouse');
  process.exit(1);
}

const report = JSON.parse(readFileSync(tmpFile, 'utf-8'));

const failedAudits = Object.values(report.audits)
  .filter((a) => a.score !== null && a.score < 1)
  .sort((a, b) => a.score - b.score)
  .slice(0, 20)
  .map((a) => ({
    id: a.id,
    title: a.title,
    score: Math.round(a.score * 100),
    displayValue: a.displayValue || null,
  }));

const summary = full ? {
  url: report.finalUrl,
  fetchTime: report.fetchTime,
  scores: Object.fromEntries(
    Object.entries(report.categories).map(([key, cat]) => [key, Math.round(cat.score * 100)])
  ),
  coreWebVitals: {
    LCP: report.audits['largest-contentful-paint']?.displayValue,
    FCP: report.audits['first-contentful-paint']?.displayValue,
    CLS: report.audits['cumulative-layout-shift']?.displayValue,
    TBT: report.audits['total-blocking-time']?.displayValue,
    SI:  report.audits['speed-index']?.displayValue,
    FID: report.audits['max-potential-fid']?.displayValue,
  },
  failedAudits,
} : { failedAudits };

console.log(JSON.stringify(summary, null, 2));
try { unlinkSync(tmpFile); } catch {}
