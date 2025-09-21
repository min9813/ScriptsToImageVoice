import { chromium, Page, Locator } from 'playwright';
import fs from 'fs/promises';

const userDataDir = './.user-data';        // ← setupLogin.ts と同じ
const CHAT_URL = 'https://chatgpt.com/';   // 新ドメインが安定

const generatePrompt = (image_prompt: string) => {
    return '詳細なアニメの美意識の画像を作成してください。表情豊かな瞳、なめらかな網掛けセルの色使い、はっきりした線画を使用します。' +
    'アニメのシーンに典型的な身ぶりと雰囲気で、心情と登場人物の存在を強調してください。' +
    image_prompt +
    '顔は全体の上1/3に配置してください'+
    ' W:H=9:16, W:H=9:16, W:H=9:16, W:H=9:16';
}

// ======== ここを変更するとプロンプトの既定値を変えられます =========
const defaultPrompts = [
//   generatePrompt('アニメ風の男子生徒が、少し離れた場所にいる女子生徒を、照れながらでも少し俯き加減の表情でこっそり見ている教室のシーン'),
//   generatePrompt('カフェで向かい合って座るアニメ風の男女。女性は微笑んでいるが、男性は何か言いたげに口ごもっている.男性は女性に対して少し照れている'),
// generatePrompt('好きな人が告白してこないことに悩む表情のアニメ風の女性のクローズアップ'),
// generatePrompt('アニメ風の男子生徒が、少し照れながらも真剣な表情で何かを考えている'),
// generatePrompt('男子生徒が、友人たちにからかわれて頭を抱えている、コミカルで恥ずかしそうなシーン'),
generatePrompt('文化祭準備に打ち込んでいる男子'),
generatePrompt('タイミングを逃して絶望した表情で呆然としている男子'),
];
// PROMPTS='["1つ目","2つ目"]' のように JSON で渡せます
const prompts: string[] = (() => {
  try {
    if (process.env.PROMPTS) return JSON.parse(process.env.PROMPTS);
  } catch { /* ignore */ }
  return defaultPrompts;
})();
const KEEP_OPEN = process.env.KEEP_OPEN === 'true';
// ===============================================================

async function waitAndClickAny(page: Page, selectors: string[]) {
  for (const sel of selectors) {
    const loc = page.locator(sel).first();
    if (await loc.isVisible().catch(() => false)) {
      await loc.click({ delay: 20 });
      return true;
    }
    try {
      await loc.waitFor({ state: 'visible', timeout: 1200 });
      await loc.click({ delay: 20 });
      return true;
    } catch { /* next */ }
  }
  return false;
}

async function getComposer(page: Page): Promise<Locator | null> {
  const candidates = [
    'div[contenteditable="true"][role="textbox"]',
    'div[contenteditable="true"][data-lexical-editor="true"]',
    'div[contenteditable="true"]',
    'div[role="textbox"]',
    '[data-testid="composer:input"] textarea',
    'footer textarea',
    'textarea[placeholder*="Message"]',
    'textarea[placeholder*="メッセージ"]',
  ];
  for (const sel of candidates) {
    const loc = page.locator(sel).last();
    if ((await loc.count()) > 0 && await loc.isVisible().catch(() => false)) return loc;
  }
  return null;
}

async function goToNewChat(page: Page) {
  await page.goto(CHAT_URL, { waitUntil: 'domcontentloaded' });
  console.log('goto chat and wait for networkidle');
  await page.waitForLoadState('networkidle').catch(() => {});
  console.log('networkidle done, wait and click any');
  // 軽いダイアログ閉じ
  await waitAndClickAny(page, [
    'button:has-text("OK")','button:has-text("Okay")','button:has-text("Got it")',
    'button:has-text("了解")','button:has-text("同意")','button:has-text("Accept")',
    'button:has-text("I agree")','button[aria-label="Close"]','[data-testid="close-button"]',
  ]);

  console.log('close any done');

  // 新規チャット誘導（UI差分に備えて複数）
  await waitAndClickAny(page, [
    '[data-testid="new-chat-button"]',
    '[data-testid="left-nav-new-chat-button"]',
    'button:has-text("New chat")',
    'a:has-text("New chat")',
    'a[href="/"]',
    'a[href*="?temporary-chat=true"]',
  ]).catch(() => {});
  await page.waitForTimeout(800);
}

async function countAssistantMessages(page: Page): Promise<number> {
    const selectors = [
      '[data-message-author-role="assistant"]',
      '[data-testid="assistant-message"]',
      '[data-author="assistant"]',
      'main article', // 最後の保険（ユーザーと混在するUIには注意）
    ];
    for (const s of selectors) {
      const n = await page.locator(s).count();
      if (n > 0) return n;
    }
    return 0;
  }

async function sendPrompt(page: Page, prompt: string) {
  const comp = await getComposer(page);
  if (!comp) throw new Error('メッセージ入力欄が見つかりませんでした。');
  const tag = (await comp.evaluate(el => el.tagName.toLowerCase()));
  if (tag === 'textarea') {
    await comp.click({ delay: 20 });
    await comp.fill('');
    await comp.type(prompt, { delay: 6 });
    console.log('sent prompt. Start push enter');
    await comp.press('Enter');
    console.log('sent prompt. End push enter');
  } else {
    await comp.click({ delay: 20 });
    await page.keyboard.type(prompt, { delay: 4 });
    console.log('sent prompt. Start push enter');
    await page.keyboard.press('Enter');
    console.log('sent prompt. End push enter');
  }
}

// 直近のアシスタントメッセージ要素を推定（UI変更に強いようにゆるめに掴む）
async function getLastAssistantBlock(page: Page): Promise<Locator | null> {
  const candidates = [
    // message コンテナに役割/データ属性がついているケース
    '[data-message-author-role="assistant"]',
    '[data-testid="assistant-message"]',
    '[data-author="assistant"]',
    // Fallback: メッセージ群の最後のカード
    'main article:has(img), main article:has([role="img"])',
    'main article',
    'article',
  ];
  for (const sel of candidates) {
    const loc = page.locator(sel).last();
    if ((await loc.count()) > 0) return loc;
  }
  return null;
}

// 画像生成の完了を待つ：新しい画像が現れ、すべて読み込み完了し、しばらく静止
async function waitForNewAssistantMessageThenComplete(
    page: Page,
    prevCount: number,
    timeoutMs = 180_000
  ) {
    const t0 = Date.now();
    page.setDefaultTimeout(0); // 自前のループで管理
  
    // A) 新しいアシスタントメッセージが増えるまで待つ
    let newMsg: Locator | null = null;
    while (Date.now() - t0 < timeoutMs) {
      if ((await countAssistantMessages(page)) > prevCount) {
        newMsg = await getLastAssistantBlock(page);
        break;
      }
      await page.waitForTimeout(250);
    }
    if (!newMsg) throw new Error('新しいアシスタントメッセージが増えません（タイムアウト）。');

    console.log('newMsg found in アシスタントメッセージ');
  
    // B) 画像が「すべてロード完了」になるまで待つ
    //    - evaluateAll で「必要最小限の値」だけ取り出す（重いオブジェクトは返さない）
    //    - 毎ループで newMsg を取り直し（DOM 差し替え対策）
    console.log('img start to wait for done');
    const deadlineImgs = Date.now() + timeoutMs;
    const invalidSrc = /data:image\/svg|placeholder|spinner/i;
    while (Date.now() < deadlineImgs) {
      newMsg = await getLastAssistantBlock(page);
      if (!newMsg) { await page.waitForTimeout(300); continue; }
  
      try { await newMsg.scrollIntoViewIfNeeded(); } catch {}
  
      const stats = await newMsg.locator('img').evaluateAll((nodes) => {
        const imgs = nodes as HTMLImageElement[];
        if (imgs.length === 0) return { ok:false, total:0, good:0 };
        let good = 0;
        for (const img of imgs) {
          if (
            img.complete &&
            img.naturalWidth > 4 &&
            img.naturalHeight > 4 &&
            img.src && !/data:image\/svg|placeholder|spinner/i.test(img.src)
          ) good++;
        }
        return { ok: good>0 && good===imgs.length, total: imgs.length, good };
      }).catch(() => ({ ok:false, total:0, good:0 })); // 差し替え中はやり直し
  
      if (stats.ok) {
        // 追加で「画像が作成されました」等の完了合図 or ダウンロードUI を確認
        const doneText = await newMsg.getByText(/画像が作成されました|image created|生成が完了/i).first().isVisible().catch(() => false);
        const hasDL = await newMsg.locator('button:has-text("Download"), button:has-text("保存"), a[download]').first().isVisible().catch(() => false);
        if (doneText || hasDL) break;
      }
      await page.waitForTimeout(500);
    }

    console.log('img done to wait for done');
  
    // C) “短時間の静止” を MutationObserver で確認（innerHTML 比較をやめる）
    newMsg = await getLastAssistantBlock(page);
    if (!newMsg) throw new Error('アシスタントメッセージが特定できませんでした（差し替え）。');
  
    console.log('newMsg found in アシスタントメッセージ');
    const calmOk = await newMsg.evaluate(async (el) => {
      // 3秒間ミューテーションが来なければ静止とみなす（上限 30 秒）
      const calmMs = 3000, limitMs = 30000;
      return await new Promise<boolean>((resolve) => {
        let timer: number | null = null;
        const done = (ok: boolean) => { if (timer) clearTimeout(timer); obs.disconnect(); resolve(ok); };
        const obs = new MutationObserver(() => {
          // 変化が来るたびに「3秒後に OK」をリセット
          if (timer) clearTimeout(timer);
          timer = window.setTimeout(() => done(true), calmMs);
        });
        obs.observe(el, { childList: true, subtree: true, attributes: true, characterData: true });
        // すでに更新が止まっている場合にも 3秒後に OK になるよう最初のタイマーをセット
        timer = window.setTimeout(() => done(true), calmMs);
        // どれだけ更新が続いても 30 秒で諦める
        window.setTimeout(() => done(true), limitMs);
      });
    }).catch(() => false);
    if (!calmOk) throw new Error('静止の確認に失敗しました。');
  
    // D) 送信欄が入力可能になるまで待つ（Enter 空振り防止）
    console.log('sendable start to wait for done');
    const composer = await getComposer(page);
    if (composer) {
      try { await composer.scrollIntoViewIfNeeded(); } catch {}
      const end = Date.now() + 15000;
      while (Date.now() < end) {
        const enabled = await composer.evaluate((el) => {
          const ce = (el as HTMLElement).getAttribute('contenteditable');
          const dis = (el as HTMLElement).getAttribute('aria-disabled');
          const style = window.getComputedStyle(el as HTMLElement);
          return (ce !== 'false') && (dis !== 'true') && style.pointerEvents !== 'none';
        }).catch(() => false);
        if (enabled) break;
        await page.waitForTimeout(300);
      }
    }

    console.log('sendable done to wait for done');
  
    return newMsg!;
  }
  

// 直近のアシスタントの画像を全て保存
async function saveImagesFromBlock(page: Page, block: Locator, outDir: string, prefix: string) {
    console.log('saveImagesFromBlock start');
  await fs.mkdir(outDir, { recursive: true });
  const imgs = block.locator('img');
  const count = await imgs.count();
  console.log('saveImagesFromBlock count', count);
  let saved = 0;
  for (let i = 0; i < count; i++) {
    console.log('saveImagesFromBlock nth', i);
    const img = imgs.nth(i);
    // srcset 対応：一番解像度が高そうなURLを選ぶ
    const { src, srcset } = await img.evaluate((el: HTMLImageElement) => ({ src: el.src, srcset: el.srcset }));
    let url = src;
    if (srcset) {
      const last = srcset.split(',').map(s => s.trim()).pop();
      if (last) url = last.split(' ')[0] || url;
    }
    if (!url) continue;

    // ブラウザ内で fetch → ArrayBuffer → base64 に変換して取り出す
    const res = await page.evaluate(async (u) => {
      const r = await fetch(u);
      const buf = await r.arrayBuffer();
      const ct = r.headers.get('content-type') || '';
      const b64 = btoa(String.fromCharCode(...new Uint8Array(buf)));
      return { b64, ct };
    }, url);

    const ext = (() => {
      if (res.ct.includes('image/png')) return 'png';
      if (res.ct.includes('image/jpeg')) return 'jpg';
      if (res.ct.includes('image/webp')) return 'webp';
      if (res.ct.includes('image/gif')) return 'gif';
      return 'bin';
    })();

    const filePath = `${outDir}/${prefix}_${i + 1}.${ext}`;
    await fs.writeFile(filePath, Buffer.from(res.b64, 'base64'));
    console.log(`画像保存: ${filePath}`);
    saved++;
  }
  if (saved === 0) {
    // 念のため全体スクショも
    await page.screenshot({ path: `${outDir}/${prefix}_fallback.png`, fullPage: true });
    console.warn(`画像URLを抽出できませんでした。スクリーンショットを保存しました。`);
  }
}

async function main() {
  const browser = await chromium.launchPersistentContext(userDataDir, {
    headless: false,
    viewport: { width: 1280, height: 900 },
    args: ['--disable-blink-features=AutomationControlled'],
  });
  const page = await browser.newPage();

  try {
    console.log('goToNewChat');
    await goToNewChat(page);
    console.log('opened new chat');

    for (let idx = 0; idx < prompts.length; idx++) {
        const p = prompts[idx];
        console.log(`送信中 [${idx + 1}/${prompts.length}]: ${p}`);
      
        const before = await countAssistantMessages(page);   // ★ 追加
        await sendPrompt(page, p);
      
        const block = await waitForNewAssistantMessageThenComplete(page, before, 300_000); // ★ 置き換え
        await saveImagesFromBlock(page, block, './artifacts', `gen${String(idx + 1).padStart(2, '0')}`);
      
        await page.waitForTimeout(800);
    }

    console.log('すべて完了。artifacts/ を確認してください。');

    if (KEEP_OPEN) {
      console.log('KEEP_OPEN=true のため、ブラウザを開いたままにします（Ctrl+Cで終了）。');
      // eslint-disable-next-line no-constant-condition
      while (true) { await page.waitForTimeout(1000); }
    }
  } catch (e: any) {
    await fs.mkdir('./artifacts', { recursive: true });
    await fs.writeFile('./artifacts/error.html', await page.content()).catch(() => {});
    await page.screenshot({ path: './artifacts/error.png', fullPage: true }).catch(() => {});
    console.error('エラー:', e?.message || e);
    console.error('artifacts/error.* を確認してください。');
  } finally {
    if (!KEEP_OPEN) await browser.close();
  }
}

main().catch(err => { console.error(err); process.exit(1); });
