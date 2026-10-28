/*
 * Точка входа клиентских скриптов, общих для всех страниц.
 * Каждый модуль сам проверяет, есть ли на странице его разметка.
 */
import { initSmoothScroll } from './scroll';
import { initHeader } from './header';
import { initPlayback, initReveal } from './reveal';
import { initIntents } from './intent';

initSmoothScroll();
initHeader();
initReveal();
initPlayback();
initIntents();

// Модули тяжёлых секций грузятся только там, где они есть.
if (document.querySelector('[data-k-stage]')) void import('./k/stage').then((m) => m.initKStage());
if (document.querySelector('[data-services]')) void import('./services').then((m) => m.initServices());
if (document.querySelector('[data-architect]')) void import('./architect').then((m) => m.initArchitect());
if (document.querySelector('[data-contact-form]')) void import('./contact').then((m) => m.initContactForms());
if (document.querySelector('[data-tabs]')) void import('./tabs').then((m) => m.initTabs());
