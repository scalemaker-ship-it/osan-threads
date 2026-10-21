// Threads API: 영상/이미지는 공개 URL 필요(hosting.js로 임시 업로드), 텍스트는 바로 게시.
const axios = require('axios');
const G = 'https://graph.threads.net';
const SCOPES = 'threads_basic,threads_content_publish';

function authUrl({ apps, redirectUri, state }) {
  if (!apps.threads?.appId) throw new Error('Threads 앱 ID가 설정되지 않았습니다(설정 > 개발자 앱).');
  const p = new URLSearchParams({ client_id: apps.threads.appId, redirect_uri: redirectUri, scope: SCOPES, response_type: 'code', state });
  return `https://threads.net/oauth/authorize?${p}`;
}
async function exchange({ apps, redirectUri, code }) {
  const t = await axios.post(`${G}/oauth/access_token`, new URLSearchParams({ client_id: apps.threads.appId, client_secret: apps.threads.appSecret, grant_type: 'authorization_code', redirect_uri: redirectUri, code }), { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } });
  const ll = await axios.get(`${G}/access_token`, { params: { grant_type: 'th_exchange_token', client_secret: apps.threads.appSecret, access_token: t.data.access_token } });
  const accessToken = ll.data.access_token;
  const me = await axios.get(`${G}/v1.0/me`, { params: { fields: 'id,username,threads_profile_picture_url', access_token: accessToken } });
  return { accessToken, userId: me.data.id, name: me.data.username, handle: '@' + me.data.username, avatar: me.data.threads_profile_picture_url || null, expiresAt: Date.now() + (ll.data.expires_in || 5184000) * 1000 };
}
async function refreshIfNeeded({ account, save }) {
  // 장기 토큰은 24시간 지난 뒤부터 갱신 가능, 만료 7일 전에 갱신
  if ((account.expiresAt || 0) - Date.now() > 7 * 86400000) return account.accessToken;
  try {
    const r = await axios.get(`${G}/refresh_access_token`, { params: { grant_type: 'th_refresh_token', access_token: account.accessToken } });
    const next = { ...account, accessToken: r.data.access_token, expiresAt: Date.now() + (r.data.expires_in || 5184000) * 1000 };
    save?.(next);
    return next.accessToken;
  } catch { return account.accessToken; }
}
async function waitContainer(id, token, onProgress) {
  for (let i = 0; i < 60; i++) {
    await new Promise((r) => setTimeout(r, 4000));
    const s = await axios.get(`${G}/v1.0/${id}`, { params: { fields: 'status,error_message', access_token: token } });
    onProgress?.(50 + Math.min(i, 40));
    if (s.data.status === 'FINISHED') return;
    if (s.data.status === 'ERROR') throw new Error('Threads 처리 실패: ' + s.data.error_message);
  }
  throw new Error('Threads 처리 시간 초과');
}
// media: { type: 'VIDEO'|'IMAGE'|'TEXT', url }
async function publish({ account, save, text, media, onProgress }) {
  const token = await refreshIfNeeded({ account, save });
  const params = { access_token: token, text: (text || '').slice(0, 500) };
  if (media?.type === 'VIDEO') { params.media_type = 'VIDEO'; params.video_url = media.url; }
  else if (media?.type === 'IMAGE') { params.media_type = 'IMAGE'; params.image_url = media.url; }
  else params.media_type = 'TEXT';
  const c = await axios.post(`${G}/v1.0/${account.userId}/threads`, null, { params });
  onProgress?.(40);
  if (params.media_type !== 'TEXT') await waitContainer(c.data.id, token, onProgress);
  else await new Promise((r) => setTimeout(r, 1500));
  const pub = await axios.post(`${G}/v1.0/${account.userId}/threads_publish`, null, { params: { creation_id: c.data.id, access_token: token } });
  let url = 'https://www.threads.net/' + account.handle;
  try { const pl = await axios.get(`${G}/v1.0/${pub.data.id}`, { params: { fields: 'permalink', access_token: token } }); url = pl.data.permalink || url; } catch {}
  onProgress?.(100);
  return { id: pub.data.id, url };
}
// Meta 개발자 콘솔 "사용자 토큰 생성기"로 받은 장기 토큰을 그대로 등록(앱 키/리다이렉트 불필요)
async function fromToken({ accessToken }) {
  const tok = String(accessToken || '').trim();
  if (!/^TH[A-Za-z0-9_-]{20,}$/.test(tok)) throw new Error('Threads 토큰 형식이 아닙니다(TH로 시작)');
  const me = await axios.get(`${G}/v1.0/me`, { params: { fields: 'id,username,threads_profile_picture_url', access_token: tok } });
  return { accessToken: tok, userId: me.data.id, name: me.data.username, handle: '@' + me.data.username, avatar: me.data.threads_profile_picture_url || null, expiresAt: Date.now() + 60 * 86400000, mode: 'api', via: 'token' };
}
module.exports = { authUrl, exchange, publish, fromToken, SCOPES };
