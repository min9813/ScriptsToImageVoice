/*
# 1) 既定プロジェクト "default" で既定プロンプトを処理
npx ts-node generateImageLoop_checkpoint.ts

# 2) プロジェクトを明示して実行（env or CLIどちらでもOK）
PROJECT=my-anime-campaign npx ts-node generateImageLoop_checkpoint.ts
# または
npx ts-node generateImageLoop_checkpoint.ts --project my-anime-campaign

# 3) プロンプト集合をファイルで管理（推奨）
#    projects/my-anime-campaign/prompts.json に JSON配列で用意
#    例: ["画像を作成してください：…","画像を作成してください：…"]
PROJECT=my-anime-campaign npx ts-node generateImageLoop_checkpoint.ts

# 4) 一度処理したら runs/<PROJECT>/status.json に記録されるので、
#    次回再開時は success 済みプロンプトは自動で SKIP されるs


*/

import { chromium, Page, BrowserContext, Locator } from 'playwright';
import fs from 'fs/promises';
import path from 'path';

const generatePrompt = (image_prompt: string) => {
    return '詳細なアニメの美意識の画像を作成してください。表情豊かな瞳、なめらかな網掛けセルの色使い、はっきりした線画を使用します。' +
    'アニメのシーンに典型的な身ぶりと雰囲気で、心情と登場人物の存在を強調してください。' +
    image_prompt +
    ' 顔は全体の上1/3に配置してください'+
    ' W:H=9:16, W:H=9:16, W:H=9:16, W:H=9:16';
}

// ==================== 設定（最低限のデフォルト） ====================
const defaultPrompts = [
  generatePrompt('アニメ風の男子生徒が、少し離れた場所にいる女子生徒を、照れながらでも少し俯き加減の表情でこっそり見ている教室のシーン'),
  generatePrompt('カフェで向かい合って座るアニメ風の男女。女性は微笑んでいるが、男性は何か言いたげに口ごもっている.男性は女性に対して少し照れている'),
  generatePrompt('好きな人が告白してこないことに悩む表情のアニメ風の女性のクローズアップ'),
  generatePrompt('アニメ風の男子生徒が、少し照れながらも真剣な表情で何かを考えている'),
  generatePrompt('男子生徒が、友人たちにからかわれて頭を抱えている、コミカルで恥ずかしそうなシーン'),
  generatePrompt('文化祭準備に打ち込んでいる男子'),
  generatePrompt('タイミングを逃して絶望した表情で呆然としている男子'),
];

const CHAT_URL = 'https://chatgpt.com/';
const userDataDir = './.user-data';

const CLICK_PER_SELECTOR_TIMEOUT = 400;     // goToNewChat での各セレクタ待ち
const NEWCHAT_TOTAL_BUDGET = 3500;          // goToNewChat の全体上限
const GENERATION_TIMEOUT = 180_000;         // 1プロンプトの生成完了待ち上限
const CALM_MS = 3000;                       // DOM 静止要求
const CALM_LIMIT_MS = 30_000;               // 静止待ち上限
const KEEP_OPEN = process.env.KEEP_OPEN === 'true';
// ====================================================================

// ==== 便利関数: プロジェクト名の取得（env or CLI） ====
function resolveProjectName(): string {
  const fromEnv = process.env.PROJECT?.trim();
  const argv = process.argv;
  const idx = argv.findIndex(a => a === '--project' || a === '-p');
  const fromArg = idx >= 0 ? argv[idx + 1] : undefined;
  return (fromArg || fromEnv || 'default').replace(/[^\w.-]/g, '_');
}

// ==== 便利関数: JSON 安全読み書き ====
async function readJson<T>(p: string, fallback: T): Promise<T> {
  try {
    const s = await fs.readFile(p, 'utf-8');
    return JSON.parse(s) as T;
  } catch { return fallback; }
}
async function writeJson(p: string, data: unknown) {
  await fs.mkdir(path.dirname(p), { recursive: true });
  await fs.writeFile(p, JSON.stringify(data, null, 2));
}

// ==== 状態ファイルの型・操作 ====
type ItemStatus = 'success' | 'failed';

interface RunItem {
  prompt: string;
  status: ItemStatus;
  attempt_count: number;
  started_at: string;
  finished_at: string;
  outputs?: string[];     // 保存した画像パス
  last_error?: string;    // 失敗時
}

interface RunStatus {
  project: string;
  updated_at: string;
  items: RunItem[];
}

function nowIso() {
  return new Date().toISOString();
}

async function loadPrompts(project: string): Promise<string[]> {
  // 1) PROMPTS env（JSON配列）
  if (process.env.PROMPTS) {
    try { return JSON.parse(process.env.PROMPTS); } catch { /* fallthrough */ }
  }
  // 2) projects/<project>/prompts.json（JSON配列）
  const projFile = path.join('projects', project, 'prompts.json');
  const arr = await readJson<string[]>(projFile, []);
  
  if (arr.length > 0) {
    // 各要素にgeneratePrompt関数を適用
    return arr;
  }

  // 3) デフォルト
  return defaultPrompts;
}

async function loadStatus(project: string): Promise<RunStatus> {
  const statusPath = path.join('runs', project, 'status.json');
  return readJson<RunStatus>(statusPath, { project, updated_at: nowIso(), items: [] });
}

async function appendStatus(project: string, entry: RunItem) {
  const statusPath = path.join('runs', project, 'status.json');
  const st = await loadStatus(project);
  // 既存の同一プロンプトの最新 status を上書き（attempt_count 更新を許容）
  const idx = st.items.findIndex(it => it.prompt === entry.prompt);
  if (idx >= 0) {
    st.items[idx] = entry;
  } else {
    st.items.push(entry);
  }
  st.updated_at = nowIso();
  await writeJson(statusPath, st);
}

async function appendSentPrompt(project: string, prompt: string) {
  const sentPath = path.join('runs', project, 'send_prompts.json');
  const sentPrompts = await readJson<string[]>(sentPath, []);
  
  // 重複チェック（文字列比較）
  if (!sentPrompts.includes(prompt)) {
    sentPrompts.push(prompt);
    await writeJson(sentPath, sentPrompts);
  }
}

async function loadSentPrompts(project: string): Promise<string[]> {
  const sentPath = path.join('runs', project, 'send_prompts.json');
  return readJson<string[]>(sentPath, []);
}

async function buildSkipSet(project: string, status: RunStatus): Promise<Set<string>> {
  // 成功済みプロンプトをスキップ
  const successPrompts = status.items.filter(it => it.status === 'success').map(it => it.prompt);
  
  // 送信済みプロンプトもスキップ（文字列比較）
  const sentPrompts = await loadSentPrompts(project);
  
  // 両方を合わせてスキップセットを作成
  const allSkipPrompts = [...new Set([...successPrompts, ...sentPrompts])];
  return new Set(allSkipPrompts);
}

// ============== Playwright 操作のヘルパ群 ==============
async function fastClickAny(page: Page, selectors: string[], totalBudgetMs = NEWCHAT_TOTAL_BUDGET) {
  console.log('start to fastClickAny totalBudgetMs=', totalBudgetMs);
  const start = Date.now();
  for (const sel of selectors) {
    console.log('start to fastClickAny sel=', sel);
    if (Date.now() - start > totalBudgetMs) break;
    const loc = page.locator(sel).first();
    console.log('start to fastClickAny loc=', loc);
    try {
      await Promise.race([
        loc.waitFor({ state: 'visible', timeout: CLICK_PER_SELECTOR_TIMEOUT }),
        page.waitForTimeout(CLICK_PER_SELECTOR_TIMEOUT),
      ]);
      if (await loc.isVisible().catch(() => false)) {
        await loc.click({ delay: 10 }).catch(() => {});
        return true;
      }
    } catch { /* next */ }
    console.log('end to fastClickAny sel=', sel);
  }
  console.log('end to fastClickAny');
  return false;
}

async function getComposer(page: Page): Promise<Locator | null> {
  const cands = [
    'div[contenteditable="true"][role="textbox"]',
    'div[contenteditable="true"][data-lexical-editor="true"]',
    'div[contenteditable="true"]',
    'div[role="textbox"]',
    '[data-testid="composer:input"] textarea',
    'footer textarea',
    'textarea[placeholder*="Message"]',
    'textarea[placeholder*="メッセージ"]',
  ];
  for (const s of cands) {
    const l = page.locator(s).last();
    if ((await l.count()) > 0 && await l.isVisible().catch(() => false)) return l;
  }
  return null;
}
async function getLastAssistantBlock(page: Page): Promise<Locator | null> {
  const cands = [
    '[data-message-author-role="assistant"]',
    '[data-testid="assistant-message"]',
    '[data-author="assistant"]',
    'main article',
    'article',
  ];
  for (const s of cands) {
    const l = page.locator(s).last();
    if ((await l.count()) > 0) return l;
  }
  return null;
}
async function countAssistantMessages(page: Page): Promise<number> {
  const sels = [
    '[data-message-author-role="assistant"]',
    '[data-testid="assistant-message"]',
    '[data-author="assistant"]',
    'main article',
  ];
  for (const s of sels) {
    const n = await page.locator(s).count();
    if (n > 0) return n;
  }
  return 0;
}

async function goToNewChat(page: Page) {
  console.log('start to goto', CHAT_URL);
  await page.goto(CHAT_URL, { waitUntil: 'domcontentloaded' });
  console.log('start to waitForLoadState');
  await page.waitForLoadState('networkidle').catch(() => {});
  console.log('start to fastClickAny');
  await fastClickAny(page, [
    'button:has-text("OK")','button:has-text("Okay")','button:has-text("Got it")',
    'button:has-text("了解")','button:has-text("同意")','button:has-text("Accept")',
    'button:has-text("I agree")','button[aria-label="Close"]','[data-testid="close-button"]',
  ], 1200).catch(() => {});
  console.log('start to fastClickAny 2');
  await fastClickAny(page, [
    '[data-testid="new-chat-button"]',
    '[data-testid="left-nav-new-chat-button"]',
    'button:has-text("New chat")',
    'a:has-text("New chat")',
    // 'a[href="/"]',
    // 'a[href*="?temporary-chat=true"]',
  ], NEWCHAT_TOTAL_BUDGET).catch(() => {});
  console.log('start to waitForTimeout');
  await page.waitForTimeout(300);
  console.log('end to goToNewChat');
}

async function sendPrompt(page: Page, prompt: string, project: string) {
    console.log('start to try to sendPrompt');
  const comp = await getComposer(page);
  if (!comp) throw new Error('入力欄が見つかりません。');
  try { await comp.scrollIntoViewIfNeeded(); } catch {}
  const expand_prompt = generatePrompt(prompt);
  console.log('この内容を送ります: expand_prompt=', expand_prompt);
  const tag = await comp.evaluate((el: HTMLElement) => el.tagName.toLowerCase());
  if (tag === 'textarea') {
    await comp.click({ delay: 10 });
    await comp.fill('');
    console.log('fill');
    await comp.type(expand_prompt, { delay: 4 });
    await comp.press('Enter');
    console.log('press enter');
  } else {
    await comp.click({ delay: 10 });
    console.log('fill');
    await page.keyboard.type(expand_prompt, { delay: 3 });
    await page.keyboard.press('Enter');
    console.log('press enter');
  }
  
  // プロンプト送信後にファイルに記録
  await appendSentPrompt(project, prompt);
  console.log('prompt saved to send_prompts.json:', prompt);
}

// 完了待ち（新メッセージの増加 → 画像ロード完了 → 静止 → composer有効）
async function waitForNewAssistantMessageThenComplete(page: Page, prevCount: number, timeoutMs = GENERATION_TIMEOUT) {
  const t0 = Date.now();
  let newMsg: Locator | null = null;
  while (Date.now() - t0 < timeoutMs) {
    if ((await countAssistantMessages(page)) > prevCount) {
      newMsg = await getLastAssistantBlock(page);
      break;
    }
    await page.waitForTimeout(200);
  }
  if (!newMsg) throw new Error('新しいアシスタントメッセージが増えません（タイムアウト）。');

  console.log('get new assistant message:', newMsg);

  const invalidSrc = /data:image\/svg|placeholder|spinner/i;
  const deadlineImgs = Date.now() + timeoutMs;
  while (Date.now() < deadlineImgs) {
    newMsg = await getLastAssistantBlock(page);
    if (!newMsg) { await page.waitForTimeout(250); continue; }
    try { await newMsg.scrollIntoViewIfNeeded(); } catch {}

    console.log('start to evaluateAll. get new msg', newMsg);

    const stats = await newMsg.locator('img').evaluateAll((nodes) => {
      const imgs = nodes as HTMLImageElement[];
      if (imgs.length === 0) return { ok:false, total:0, good:0 };
      let good = 0;
      for (const img of imgs) {
        if (img.complete && img.naturalWidth > 4 && img.naturalHeight > 4 && img.src && !/data:image\/svg|placeholder|spinner/i.test(img.src)) {
          good++;
        }
      }
      return { ok: good > 0 && good === imgs.length, total: imgs.length, good };
    }).catch(() => ({ ok:false, total:0, good:0 }));

    if (stats.ok) {
      const doneText = await newMsg.getByText(/画像が作成されました|image created|生成が完了/i).first().isVisible().catch(() => false);
      const hasDL = await newMsg.locator('button:has-text("Download"), button:has-text("保存"), a[download]').first().isVisible().catch(() => false);
      console.log('doneText=', doneText, 'hasDL=', hasDL);
      if (doneText || hasDL) break;
    }
    await page.waitForTimeout(2000);
  }

  newMsg = await getLastAssistantBlock(page);
  if (!newMsg) throw new Error('アシスタントメッセージが特定できませんでした。');
  console.log('newMsg=', newMsg, "check calm");
  await newMsg.evaluate(async (el: Element, args: { calmMs: number; limitMs: number }) => {
    const { calmMs: CM, limitMs: LM } = args;
    await new Promise<void>((resolve) => {
      let timer: number | null = null;
      const done = () => { if (timer) clearTimeout(timer); obs.disconnect(); resolve(); };
      const obs = new MutationObserver(() => {
        if (timer) clearTimeout(timer);
        timer = window.setTimeout(done, CM);
      });
      obs.observe(el, { childList: true, subtree: true, attributes: true, characterData: true });
      timer = window.setTimeout(done, CM);
      window.setTimeout(done, LM);
    });
  }, { calmMs: CALM_MS, limitMs: CALM_LIMIT_MS });

  const comp = await getComposer(page);
  if (comp) {
    try { await comp.scrollIntoViewIfNeeded(); } catch {}
    const end = Date.now() + 10_000;
    while (Date.now() < end) {
      const enabled = await comp.evaluate((el: HTMLElement) => {
        const ce = el.getAttribute('contenteditable');
        const dis = el.getAttribute('aria-disabled');
        const style = window.getComputedStyle(el);
        return (ce !== 'false') && (dis !== 'true') && style.pointerEvents !== 'none';
      }).catch(() => false);
      if (enabled) break;
      await page.waitForTimeout(250);
    }
  }

  return newMsg;
}

async function saveImagesFromBlock(page: Page, block: Locator, outDir: string, prefix: string) {
  console.log('start to saveImagesFromBlock');
  await fs.mkdir(outDir, { recursive: true });
  const imgs = block.locator('img');
  const count = await imgs.count();
  console.log('end to saveImagesFromBlock count=', count);
  const savedPaths: string[] = [];
  for (let i = 0; i < count; i++) {
    const img = imgs.nth(i);
    console.log('start to saveImagesFromBlock img i=', i);
    const { src, srcset } = await img.evaluate((el: HTMLImageElement) => ({ src: el.src, srcset: el.srcset }));
    let url = src;
    if (srcset) {
      const last = srcset.split(',').map(s => s.trim()).pop();
      if (last) url = last.split(' ')[0] || url;
    }
    if (!url) continue;
    console.log('start to fetch page');
    const res = await page.evaluate(async (u) => {
        const r = await fetch(u);
        const blob = await r.blob();
        const ct = r.headers.get('content-type') || blob.type || '';
        const b64 = await new Promise<string>((resolve, reject) => {
          const fr = new FileReader();
          fr.onloadend = () => resolve((fr.result as string).split(',')[1] || '');
          fr.onerror = reject;
          fr.readAsDataURL(blob);
        });
        return { b64, ct };
      }, url);
    console.log('finish to fetch page');
    const ext = res.ct.includes('png') ? 'png' :
                res.ct.includes('jpeg') || res.ct.includes('jpg') ? 'jpg' :
                res.ct.includes('webp') ? 'webp' :
                res.ct.includes('gif') ? 'gif' : 'bin';
    const filePath = path.join(outDir, `${prefix}_${i + 1}.${ext}`);
    await fs.writeFile(filePath, Buffer.from(res.b64, 'base64'));
    savedPaths.push(filePath);
  }
  if (savedPaths.length === 0) {
    const fp = path.join(outDir, `${prefix}_fallback.png`);
    await page.screenshot({ path: fp, fullPage: true });
    savedPaths.push(fp);
  }
  return savedPaths;
}

// ================== ランチャ & 1プロンプト実行 ==================
async function launch(): Promise<BrowserContext> {
  return chromium.launchPersistentContext(userDataDir, {
    headless: false,
    viewport: { width: 1280, height: 900 },
    args: ['--disable-blink-features=AutomationControlled'],
  });
}

async function runOnePrompt(project: string, ctx: BrowserContext, prompt: string, index: number, page: Page) {
  console.log('start to runOnePrompt', prompt);
  const runBase = path.join('runs', project);
  const artBase = path.join('artifacts', project);
  await fs.mkdir(runBase, { recursive: true });
  await fs.mkdir(artBase, { recursive: true });

let crashed = false;
    page.on('crash', () => { crashed = true; });

  let attempts = 1;
    const startIso = nowIso();
    // 既存attemptがあれば拾って+1（任意：簡易版は常に1でOK）
  const existing = await loadStatus(project);
  const prev = existing.items.find(it => it.prompt === prompt);
    if (prev) attempts = prev.attempt_count + 1;
    try {
    console.log('start to countAssistantMessages');
    const before = await countAssistantMessages(page);
    console.log('end to countAssistantMessages', before);
    console.log('start to sendPrompt', prompt);
    await sendPrompt(page, prompt, project);
    console.log('end to sendPrompt', prompt);
    const block = await waitForNewAssistantMessageThenComplete(page, before, GENERATION_TIMEOUT);
    console.log('end to waitForNewAssistantMessageThenComplete', block);
    const prefix = `gen${String(index + 1).padStart(3, '0')}`;

    let outputs: string[] = [];
    try {
        outputs = await saveImagesFromBlock(page, block, artBase, prefix);
        console.log('end to saveImagesFromBlock', outputs);
    } catch (e: any) {
        console.error('error to saveImagesFromBlock', e);
        outputs = [];
    }

    // 成功記録（即フラッシュ）
    await appendStatus(project, {
      prompt,
      status: 'success',
      attempt_count: attempts,
      started_at: startIso,
      finished_at: nowIso(),
      outputs,
    });

    if (crashed) throw new Error('page crashed after generation');
  } catch (e: any) {
    // 失敗も記録（即フラッシュ）
    await appendStatus(project, {
      prompt,
      status: 'failed',
      attempt_count: attempts,
      started_at: startIso,
      finished_at: nowIso(),
      last_error: e?.message || String(e),
    });
    try {
      await fs.mkdir(path.join('artifacts', project), { recursive: true });
      await page.screenshot({ path: path.join('artifacts', project, `error_${String(index + 1).padStart(3, '0')}.png`), fullPage: true }).catch(() => {});
      await fs.writeFile(path.join('artifacts', project, `error_${String(index + 1).padStart(3, '0')}.html`), await page.content()).catch(() => {});
    } catch {}
    try { await page.close().catch(() => {}); } catch {}
    throw e; // 上位でブラウザ再起動して次へ
  }
}

// ============================ メイン ============================
async function main() {
  const project = resolveProjectName();
  const prompts = await loadPrompts(project);
  if (prompts.length === 0) {
    console.error(`プロジェクト "${project}" にプロンプトがありません。PROMPTS か projects/${project}/prompts.json を用意してください。`);
    process.exit(1);
  }

  const status = await loadStatus(project);
  const skipSet = await buildSkipSet(project, status);

  console.log(`Project: ${project}`);
  console.log(`Total prompts: ${prompts.length}, skip(success): ${skipSet.size}`);

  let ctx: BrowserContext | null = null;
  let page: Page | null = null;

  for (let i = 0; i < prompts.length; i++) {
    const p = prompts[i];

    if (skipSet.has(p)) {
      console.log(`→ SKIP (already sent or success): [${i + 1}/${prompts.length}] ${p}`);
      continue;
    }

    console.log(`=== [${i + 1}/${prompts.length}] START ===`);
    try {
      console.log('start to launch');
      if (!ctx || !page) {
        ctx = await launch();
        page = await ctx.newPage();
        page.setDefaultTimeout(0);
        page.setDefaultNavigationTimeout(0);
    
    
    
    
        console.log('start to goToNewChat');
        await goToNewChat(page);
      }
      await runOnePrompt(project, ctx, p, i, page);
      console.log(`=== [${i + 1}/${prompts.length}] DONE ===`);
    } catch (err: any) {
      console.error(`✖ FAILED: ${err?.message || err}`);
      if (ctx) { try { await ctx.close(); } catch {} ctx = null; }
      // 要望通り：失敗したプロンプトはスキップして次へ（再試行しない）
      continue;
    }
  }

  console.log('=== ALL PROMPTS PROCESSED ===');

  if (KEEP_OPEN) {
    ctx = await launch();
    const page = await ctx.newPage();
    await goToNewChat(page);
    console.log('KEEP_OPEN=true のため開いたままにします（Ctrl+Cで終了）。');
    // eslint-disable-next-line no-constant-condition
    while (true) { await page.waitForTimeout(1000); }
  }
}

main().catch(e => { console.error(e); process.exit(1); });
