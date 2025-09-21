// setupLogin.ts
import { chromium } from 'playwright';

(async () => {
  // userDataDir を指定して永続プロファイルを作る（ここにGoogle/ChatGPTのクッキーが入る）
  const userDataDir = './.user-data'; // 任意フォルダ
  const browser = await chromium.launchPersistentContext(userDataDir, {
    headless: false,               // 画面を出す
    viewport: { width: 1280, height: 900 },
    args: [
      '--disable-blink-features=AutomationControlled', // 多少の対策
    ],
  });

  const page = await browser.newPage();

  // ChatGPTトップへ
  await page.goto('https://chat.openai.com/', { waitUntil: 'domcontentloaded' });

  console.log('ブラウザが開いたら、"Continue with Google" からログインしてください。');
  console.log('ログイン後、ChatGPTのホーム/チャット画面が表示されたらウィンドウを閉じてOKです。');

  // 手動操作を待つだけ。必要ならタイムアウトを調整。
  await page.waitForTimeout(5 * 60 * 1000); // 最大5分待機（適宜短くしてOK）

  await browser.close();
})();
