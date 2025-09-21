// generateImage.ts
import { chromium, Page } from 'playwright';
import fs from 'fs/promises';

const userDataDir = './.user-data'; // setupLogin.ts と同じディレクトリを使う
const CHAT_URL = 'https://chatgpt.com/'; // 旧: https://chat.openai.com/

async function waitAndClickAny(page: Page, selectors: string[]) {
  for (const sel of selectors) {
    const el = page.locator(sel);
    if (await el.first().isVisible().catch(() => false)) {
      await el.first().click({ delay: 20 });
      return true;
    }
    // 一瞬だけ待って探す（A/Bテストや遅延描画対策）
    const found = await page.locator(sel).first().waitFor({ state: 'visible', timeout: 1500 }).then(
      async () => { await page.locator(sel).first().click({ delay: 20 }); return true; },
      () => false
    );
    if (found) return true;
  }
  return false;
}

async function getComposerLocator(page: Page) {
  // 入力欄候補（新→旧の順に強い順で）
  const candidates = [
    // もっとも汎用的（Lexical/ProseMirror 系）
    'div[contenteditable="true"][role="textbox"]',
    'div[contenteditable="true"][data-lexical-editor="true"]',
    'div[contenteditable="true"]',

    // ARIA ロール系
    'div[role="textbox"]',

    // 旧 UI
    '[data-testid="composer:input"] textarea',
    'footer textarea',
    'textarea[placeholder*="Message"]',
    'textarea[placeholder*="メッセージ"]',
  ];

  for (const sel of candidates) {
    const loc = page.locator(sel).last();
    if (await loc.count() > 0 && await loc.isVisible().catch(() => false)) {
      return loc;
    }
  }
  return null;
}

async function typePromptAndSend(page: Page, prompt: string) {
  const composer = await getComposerLocator(page);
  if (!composer) {
    throw new Error('メッセージ入力欄が見つかりませんでした。セレクタを更新してください。');
  }

  // contenteditable か textarea かで入力方法を分ける
  const tagName = await composer.evaluate(el => el.tagName?.toLowerCase());
  if (tagName === 'textarea') {
    await composer.click({ delay: 20 });
    await composer.fill('');
    await composer.type(prompt, { delay: 10 });
    await composer.press('Enter');
  } else {
    // contenteditable
    await composer.click({ delay: 20 });
    // paste っぽく一気に入れる方が安定
    await page.keyboard.type(prompt, { delay: 5 });
    await page.keyboard.press('Enter');
  }
}

async function maybeDismissPopups(page: Page) {
  // クッキー許可/規約/チュートリアルなどの軽いダイアログを閉じる
  const dismissors = [
    'button:has-text("OK")',
    'button:has-text("Okay")',
    'button:has-text("Got it")',
    'button:has-text("了解")',
    'button:has-text("同意")',
    'button:has-text("Accept")',
    'button:has-text("I agree")',
    'button[aria-label="Close"]',
    '[data-testid="close-button"]',
  ];
  await waitAndClickAny(page, dismissors).catch(() => {});
}

async function goToNewChat(page: Page) {
  // まずトップへ
  await page.goto(CHAT_URL, { waitUntil: 'domcontentloaded' });
  await page.waitForLoadState('networkidle').catch(() => {});

  await maybeDismissPopups(page);

  // 新規チャットボタン候補（左ナビ・ヘッダなど）
  const newChatSelectors = [
    '[data-testid="new-chat-button"]',
    '[data-testid="left-nav-new-chat-button"]',
    'button:has-text("New chat")',
    'a:has-text("New chat")',
    'a[href="/"]',                        // ホームに戻る
    'a[href*="?temporary-chat=true"]',    // 一時チャット誘導
  ];
  await waitAndClickAny(page, newChatSelectors).catch(() => {});
  // 遷移待ち（UI によっては不要）
  await page.waitForTimeout(1000);

  // 入力欄が出るまで少し待つ
  for (let i = 0; i < 5; i++) {
    const comp = await getComposerLocator(page);
    if (comp) return;
    await page.waitForTimeout(800);
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
    await goToNewChat(page);

    // 念のため composer 再確認
    const comp = await getComposerLocator(page);
    if (!comp) throw new Error('メッセージ入力欄が見つかりませんでした。セレクタを更新してください。');

    const prompt =
      process.env.PROMPT ||
      '画像を作成してください：映画ポスター風の猫の宇宙飛行士、ディテール豊富、ドラマチックなライティング、アスペクト比9:16';

    await typePromptAndSend(page, prompt);

    // 応答（画像）の到着待ち
    const imageSelectors = [
      'figure img',
      'img[alt*="image"]',
      '[role="img"]',
      'div:has(img)',
      'img',
    ];

    let appeared = false;
    const timeoutMs = 90_000;
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
      for (const sel of imageSelectors) {
        if (await page.locator(sel).first().isVisible().catch(() => false)) {
          appeared = true;
          break;
        }
      }
      if (appeared) break;
      await page.waitForTimeout(1000);
    }

    await fs.mkdir('./artifacts', { recursive: true });
    await page.screenshot({ path: './artifacts/result.png', fullPage: true });
    if (appeared) {
      console.log('画像らしきDOMを検出。スクリーンショット: artifacts/result.png');
    } else {
      console.warn('画像DOMは検出できず。UI変更か権限/プランの問題の可能性。スクリーンショット: artifacts/result.png');
    }
  } catch (e: any) {
    // デバッグ用に HTML とスクショを残す
    await fs.mkdir('./artifacts', { recursive: true });
    await page.screenshot({ path: './artifacts/error.png', fullPage: true }).catch(() => {});
    await fs.writeFile('./artifacts/error.html', await page.content()).catch(() => {});
    console.error('エラー:', e?.message || e);
    console.error('artifacts/error.png と artifacts/error.html を確認してください');
  } finally {
    await browser.close();
  }
}

main().catch(err => {
  console.error(err);
  process.exit(1);
});
