/* Studio 的 service worker（2026-11-06）：只做两件事——收到推送时显示通知、点通知时打开对应的页面。
   不拦截任何请求、不缓存任何东西（页面照旧每次从电脑上读）。推送本身不带内容：收到后来取 /api/push/last。 */
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));
self.addEventListener('push', e => e.waitUntil((async () => {
  let n = { title: 'Studio', body: '任务已完成', url: '/play' };
  try { const r = await fetch('/api/push/last', { credentials: 'same-origin', cache: 'no-store' }); if (r.ok) n = { ...n, ...(await r.json()) }; } catch { }
  await self.registration.showNotification(n.title || 'Studio', { body: n.body || '', tag: 'studio-job', renotify: true, icon: '/static/app-icon-512.png', badge: '/static/app-icon-512.png', data: { url: n.url || '/play' } });
})()));
self.addEventListener('notificationclick', e => {
  e.notification.close();
  const url = new URL(e.notification.data?.url || '/play', self.location.origin).href;
  e.waitUntil((async () => {
    const cs = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
    for (const c of cs) { try { await c.focus(); if (c.url !== url && 'navigate' in c) await c.navigate(url); return; } catch { } }
    await self.clients.openWindow(url);
  })());
});
