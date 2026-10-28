import Lenis from 'lenis';
import { reducedMotion } from './motion';

let lenis: Lenis | null = null;

export function getLenis(): Lenis | null {
  return lenis;
}

/** Плавная инерционная прокрутка без перехвата: нативный скролл, только сглаживание. */
export function initSmoothScroll(): void {
  if (!reducedMotion()) {
    lenis = new Lenis({ lerp: 0.11, wheelMultiplier: 0.9, autoRaf: true, anchors: false });
  }

  // Якоря: и '#x', и '/ru/#x' на текущей странице прокручиваются, а не перезагружают.
  document.addEventListener('click', (event) => {
    const link = (event.target as Element | null)?.closest<HTMLAnchorElement>('a[href*="#"]');
    if (!link || event.defaultPrevented || event.metaKey || event.ctrlKey || event.shiftKey) return;
    const url = new URL(link.href, location.href);
    if (url.pathname !== location.pathname || !url.hash) return;
    const target = url.hash === '#main' ? document.body : document.getElementById(decodeURIComponent(url.hash.slice(1)));
    if (!target) return;
    event.preventDefault();
    scrollToElement(target);
    history.pushState(null, '', url.hash === '#main' ? location.pathname : url.hash);
  });
}

export function scrollToElement(target: HTMLElement): void {
  const header = document.querySelector<HTMLElement>('[data-header]');
  const offset = target === document.body ? 0 : -(header?.offsetHeight ?? 0) + 1;
  if (lenis) {
    lenis.scrollTo(target === document.body ? 0 : target, { offset, duration: 1.4 });
  } else {
    const top = target === document.body ? 0 : target.getBoundingClientRect().top + scrollY + offset;
    scrollTo({ top, behavior: reducedMotion() ? 'auto' : 'smooth' });
  }
  // Фокус переносится в цель для клавиатуры и скринридеров.
  const focusable = target.matches('section, main, [tabindex]') ? target : null;
  if (focusable) {
    if (!focusable.hasAttribute('tabindex')) focusable.setAttribute('tabindex', '-1');
    focusable.focus({ preventScroll: true });
  }
}
