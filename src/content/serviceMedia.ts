/**
 * Видео для сцен услуг (владелец генерирует их по материалам из presentation-materials/, см. README там).
 * Пока пусто — в панелях идут SVG-сцены (ServiceScene.astro). Чтобы подключить ролик: положить
 * public/media/services/<id>.mp4 (H.264, без звука, 6–10 с, ≤ 2 МБ) и постер <id>.webp, затем добавить
 *   web: { mp4: '/media/services/web.mp4', poster: '/media/services/web.webp' },
 * Видео играет только у открытой панели в кадре и не играет при prefers-reduced-motion (виден постер).
 */
export const serviceMedia: Partial<Record<string, { mp4: string; poster: string }>> = {};
