/* Cloudflare Worker 入口：把 core.js 接上 fetch（瀏覽器的操作）與 scheduled（每天台北 08:00 叫醒 GitHub Actions）。
   機密 ALERT_KEY、GH_TOKEN 由 .github/workflows/alerts-worker-deploy.yml 用 wrangler secret put 設定，不在原始碼裡。 */
import { handleRequest, dispatchDaily } from './core.js';

export default {
  fetch(request, env) { return handleRequest(request, env); },
  scheduled(event, env, ctx) { ctx.waitUntil(dispatchDaily(env)); },
};
