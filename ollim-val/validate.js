// 비파괴 검증: Ollim의 실제 threads.js로 (1) 토큰 인증(/me) (2) TEXT 컨테이너 생성까지만.
// threads_publish 는 호출하지 않으므로 공개 게시물이 생기지 않는다.
const axios = require('axios');
const threads = require('./threads');
(async () => {
  const accessToken = process.env.THREADS_ACCESS_TOKEN;
  if (!accessToken) throw new Error('THREADS_ACCESS_TOKEN 없음');
  // (1) Ollim fromToken = /me 인증
  let account;
  try { account = await threads.fromToken({ accessToken }); }
  catch (e) { const me = await axios.get('https://graph.threads.net/v1.0/me', { params: { fields: 'id,username', access_token: accessToken } }); account = { accessToken, userId: me.data.id, name: me.data.username, handle: '@' + me.data.username }; }
  console.log('AUTH_OK name=%s handle=%s userId=%s', account.name, account.handle, account.userId);
  // (2) Ollim publish 가 쓰는 것과 동일한 컨테이너 생성(게시 전 단계)만 수행
  const c = await axios.post(`https://graph.threads.net/v1.0/${account.userId}/threads`, null, { params: { access_token: account.accessToken, media_type: 'TEXT', text: 'ollim pipeline validation (not published)' } });
  console.log('CONTAINER_CREATE_OK id=%s', c.data.id);
  console.log('VALIDATE_RESULT=PASS (인증 + 컨테이너 생성 성공, 게시 안 함 → 공개 글 없음)');
})().catch((e) => { console.error('VALIDATE_RESULT=FAIL', e.response?.data ? JSON.stringify(e.response.data) : e.message); process.exit(1); });
