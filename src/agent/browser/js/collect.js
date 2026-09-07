// Обходчик DOM. Возвращает плоский список интерактивных элементов страницы.

//

// ЕДИНСТВЕННОЕ место в проекте, где допустимы CSS-селекторы (docs/CONSTRAINTS.md §2.2).

// Здесь они описывают HTML как язык разметки, а не признаки конкретного сайта:

// ничего специфичного для какого-либо конкретного сайта тут быть не должно.

//

// Выполняется в контексте каждого фрейма. Реестр ref живёт в window этого фрейма,

// поэтому ref переживает ре-рендер: пока узел жив, он сохраняет свой номер.



(() => {

  const MAX_NAME = 120;

  const MAX_ELEMENTS = 800;

  // Сколько экранов вокруг видимой области попадает в снапшот.

  const VIEWPORT_MARGIN_SCREENS = 1;



  // ── Реестр ref ────────────────────────────────────────────────────

  // byEl -> ref даёт стабильность: тот же узел получит тот же ref.



  if (!window.__agentRegistry) {

    window.__agentRegistry = {

      byRef: new Map(),

      byEl: new WeakMap(),

      counter: 0,

    };

  }

  const registry = window.__agentRegistry;



  function refFor(el) {

    let ref = registry.byEl.get(el);

    if (ref && registry.byRef.get(ref) === el) return ref;

    ref = 'e' + ++registry.counter;

    registry.byEl.set(el, ref);

    registry.byRef.set(ref, el);

    return ref;

  }



  // ── Обход, включая open shadow DOM ────────────────────────────────



  function* walk(root) {

    const stack = [root];

    while (stack.length) {

      const node = stack.pop();

      if (!node) continue;



      if (node.nodeType === Node.ELEMENT_NODE) {

        yield node;

        // Closed shadow root отсюда недоступен — он берётся через CDP по требованию.

        if (node.shadowRoot) stack.push(node.shadowRoot);

      }



      const children = node.children;

      if (children) {

        for (let i = children.length - 1; i >= 0; i--) stack.push(children[i]);

      }

    }

  }



  // ── Интерактивность ───────────────────────────────────────────────



  const INTERACTIVE_TAGS = new Set([

    'A', 'BUTTON', 'INPUT', 'SELECT', 'TEXTAREA', 'SUMMARY', 'OPTION',

  ]);



  const INTERACTIVE_ROLES = new Set([

    'button', 'link', 'checkbox', 'radio', 'textbox', 'searchbox', 'combobox',

    'listbox', 'option', 'menuitem', 'menuitemcheckbox', 'menuitemradio',

    'tab', 'switch', 'slider', 'spinbutton', 'treeitem',

  ]);



  // Роли, которые сами не кликаются, но объясняют устройство страницы.

  const LANDMARK_ROLES = new Set(['dialog', 'alertdialog', 'alert', 'status']);



  function explicitRole(el) {

    const r = el.getAttribute('role');

    return r ? r.trim().toLowerCase().split(/\s+/)[0] : '';

  }



  function impliedRole(el) {

    const tag = el.tagName;

    if (tag === 'A') return el.hasAttribute('href') ? 'link' : '';

    if (tag === 'BUTTON' || tag === 'SUMMARY') return 'button';

    if (tag === 'SELECT') return el.multiple ? 'listbox' : 'combobox';

    if (tag === 'TEXTAREA') return 'textbox';

    if (tag === 'OPTION') return 'option';

    if (tag === 'INPUT') {

      const t = (el.type || 'text').toLowerCase();

      if (t === 'checkbox') return 'checkbox';

      if (t === 'radio') return 'radio';

      if (t === 'range') return 'slider';

      if (t === 'number') return 'spinbutton';

      if (t === 'search') return 'searchbox';

      if (['button', 'submit', 'reset', 'image'].includes(t)) return 'button';

      if (['hidden'].includes(t)) return '';

      return 'textbox';

    }

    return '';

  }



  function isInteractive(el, role, style) {

    if (el.hasAttribute('disabled') || el.getAttribute('aria-disabled') === 'true') {

      // Отключённые элементы показываем — агент должен понимать, почему не работает.

      return INTERACTIVE_TAGS.has(el.tagName) || INTERACTIVE_ROLES.has(role);

    }

    if (INTERACTIVE_TAGS.has(el.tagName)) return true;

    if (INTERACTIVE_ROLES.has(role)) return true;

    if (el.isContentEditable) return true;



    const tabindex = el.getAttribute('tabindex');

    if (tabindex !== null && parseInt(tabindex, 10) >= 0) return true;

    if (el.hasAttribute('onclick')) return true;



    // cursor:pointer один по себе шумит — половина страницы попадает под него.

    // Берём только если элемент компактный, подписан и не является обёрткой

    // над настоящим контролом: иначе рядом с каждой ссылкой появляется

    // её же span-двойник.

    if (style.cursor === 'pointer' && ownsPointer(el)) {

      const rect = el.getBoundingClientRect();

      const compact = rect.width * rect.height < 90000;

      const labelled = (el.textContent || '').trim().length > 0 || el.hasAttribute('aria-label');

      if (compact && labelled && !wrapsInteractive(el)) return true;

    }

    return false;

  }



  // cursor — наследуемое свойство. Карточка с `cursor:pointer` раздаёт его

  // всем своим потомкам, и каждый абзац внутри выглядит кликабельным: на

  // странице результатов поиска одна карточка давала дюжину ref на кусочки

  // собственного текста («12 000 000», «so'm», «Опыт 3-6 лет»). Нажать на

  // них нельзя ничего осмысленного, а место в состоянии они занимают.

  // Условие ниже оставляет только тот узел, на котором указатель объявлен:

  // у его родителя курсор другой (docs/ADR.md ADR-027).

  function ownsPointer(el) {

    const parent = el.parentElement;

    if (!parent) return true;

    try {

      return getComputedStyle(parent).cursor !== 'pointer';

    } catch {

      return true;

    }

  }



  // Обёртка над настоящим контролом — сама кликабельной не считается.

  const INNER_INTERACTIVE = 'a[href], button, input, select, textarea, [role], [tabindex]';



  function wrapsInteractive(el) {

    return el.querySelector(INNER_INTERACTIVE) !== null

      || el.closest(INNER_INTERACTIVE) !== null;

  }



  // ── Видимость и перекрытие ────────────────────────────────────────



  function isRendered(el, style, rect) {

    if (rect.width <= 1 || rect.height <= 1) return false;

    if (style.visibility === 'hidden' || style.visibility === 'collapse') return false;

    if (parseFloat(style.opacity) === 0) return false;

    if (el.hasAttribute('inert')) return false;

    if (el.getAttribute('aria-hidden') === 'true') return false;

    return true;

  }



  // Главная проверка: попадёт ли клик в этот элемент.

  // Она же бесплатно решает задачу попапов — перекрытая кнопка выпадает

  // из снапшота, а перекрывающий её баннер в него попадает.

  // Никаких списков «закрыть куки» не нужно (docs/CONSTRAINTS.md §2.2).

  function occlusion(el, rect) {

    const doc = el.ownerDocument;

    const probes = [

      [rect.left + rect.width / 2, rect.top + rect.height / 2],

      [rect.left + rect.width * 0.15, rect.top + rect.height / 2],

      [rect.left + rect.width * 0.85, rect.top + rect.height / 2],

    ];



    let blocker = null;

    for (const [x, y] of probes) {

      if (x < 0 || y < 0 || x > innerWidth || y > innerHeight) continue;

      const hit = doc.elementFromPoint(x, y);

      if (!hit) continue;

      if (hit === el || el.contains(hit) || hit.contains(el)) return { covered: false };

      blocker = hit;

    }

    if (!blocker) return { covered: false };

    return { covered: true, blocker };

  }



  // ── Доступное имя (упрощённый AccName) ────────────────────────────



  function clean(text) {

    if (!text) return '';

    const t = text.replace(/\s+/g, ' ').trim();

    return t.length > MAX_NAME ? t.slice(0, MAX_NAME - 1) + '…' : t;

  }



  function labelFromFor(el) {

    const doc = el.ownerDocument;

    if (el.id) {

      const lbl = doc.querySelector(`label[for="${CSS.escape(el.id)}"]`);

      if (lbl) return lbl.textContent;

    }

    const wrapper = el.closest('label');

    return wrapper ? wrapper.textContent : '';

  }



  function accessibleName(el) {

    const byIds = el.getAttribute('aria-labelledby');

    if (byIds) {

      const doc = el.ownerDocument;

      const parts = byIds.split(/\s+/)

        .map((id) => doc.getElementById(id))

        .filter(Boolean)

        .map((n) => n.textContent);

      const joined = clean(parts.join(' '));

      if (joined) return joined;

    }



    const aria = clean(el.getAttribute('aria-label'));

    if (aria) return aria;



    if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT') {

      const lbl = clean(labelFromFor(el));

      if (lbl) return lbl;

      const ph = clean(el.getAttribute('placeholder'));

      if (ph) return ph;

    }



    if (el.tagName === 'IMG') {

      const alt = clean(el.getAttribute('alt'));

      if (alt) return alt;

    }



    // Только собственный текст, иначе контейнер утащит текст всего поддерева.

    const own = clean(el.textContent);

    if (own && own.length <= MAX_NAME) return own;



    const title = clean(el.getAttribute('title'));

    if (title) return title;



    if (own) return own;

    return '';

  }



  // ── Состояние ─────────────────────────────────────────────────────



  function stateOf(el, role) {

    const st = {};

    if (el.hasAttribute('disabled') || el.getAttribute('aria-disabled') === 'true') {

      st.disabled = true;

    }

    const expanded = el.getAttribute('aria-expanded');

    if (expanded !== null) st.expanded = expanded === 'true';

    const selected = el.getAttribute('aria-selected');

    if (selected !== null) st.selected = selected === 'true';

    const checkedAttr = el.getAttribute('aria-checked');

    if (checkedAttr !== null) st.checked = checkedAttr === 'true';

    else if (role === 'checkbox' || role === 'radio' || role === 'switch') {

      st.checked = !!el.checked;

    }

    if (el.required || el.getAttribute('aria-required') === 'true') st.required = true;

    return st;

  }



  function valueOf(el) {

    if (el.tagName === 'SELECT') {

      const opt = el.selectedOptions && el.selectedOptions[0];

      return opt ? clean(opt.textContent) : '';

    }

    if (el.tagName === 'INPUT') {

      const t = (el.type || 'text').toLowerCase();

      if (t === 'password') return el.value ? '••••••' : '';

      if (['checkbox', 'radio', 'button', 'submit'].includes(t)) return '';

      return clean(el.value);

    }

    if (el.tagName === 'TEXTAREA') return clean(el.value);

    if (el.isContentEditable) return clean(el.textContent);

    return '';

  }



  // Подпись структуры — по ней Python схлопывает одинаковые соседние карточки.

  function signature(el, role) {

    const parent = el.parentElement;

    const parentTag = parent ? parent.tagName : '-';

    const kids = el.children.length;

    return `${role || el.tagName.toLowerCase()}|${parentTag}|${kids}|${el.hasAttribute('href') ? 'h' : ''}`;

  }



  // ── Сбор ──────────────────────────────────────────────────────────



  // Вложенные обёртки с одинаковой подписью — самый частый источник мусора:

  // карточка, её внутренний div и текстовый span дают три одинаковые строки.

  // Оставляем один: настоящий контрол важнее эвристического, при прочих

  // равных побеждает внутренний — по нему точнее попадёт клик.

  function dedupeNested(items) {

    const groups = new Map();

    for (const it of items) {

      // Ключ только по имени: вложенные обёртки часто имеют разные роли
      // (div/data/address вокруг одного текста). От ложных склеек защищает
      // проверка вложенности ниже — несвязанные элементы не тронем.
      const key = it.item.name;
      if (!groups.has(key)) groups.set(key, []);

      groups.get(key).push(it);

    }



    const dropped = new Set();

    for (const group of groups.values()) {

      if (group.length < 2) continue;

      const kept = [];

      for (const cand of group) {

        const clash = kept.find(

          (k) => k.el.contains(cand.el) || cand.el.contains(k.el),

        );

        if (!clash) { kept.push(cand); continue; }

        let winner = clash;

        if (cand.strong !== clash.strong) {

          winner = cand.strong ? cand : clash;

        } else if (clash.el.contains(cand.el)) {

          winner = cand;

        }

        const loser = winner === clash ? cand : clash;

        dropped.add(loser);

        kept[kept.indexOf(clash)] = winner;

      }

    }

    return items.filter((it) => !dropped.has(it));

  }



  const scrollY = window.scrollY || 0;

  const margin = innerHeight * VIEWPORT_MARGIN_SCREENS;

  const collected = [];

  let offscreen = 0;

  let truncated = false;



  for (const el of walk(document.documentElement)) {

    if (collected.length >= MAX_ELEMENTS) { truncated = true; break; }



    let style;

    try {

      style = getComputedStyle(el);

    } catch { continue; }

    if (style.display === 'none') continue;



    const role = explicitRole(el) || impliedRole(el);

    const landmark = LANDMARK_ROLES.has(role);

    if (!landmark && !isInteractive(el, role, style)) continue;



    const rect = el.getBoundingClientRect();

    if (!isRendered(el, style, rect)) continue;



    // Окно вокруг видимой области: остальное только считаем.

    const inWindow = rect.bottom > -margin && rect.top < innerHeight + margin;

    if (!inWindow) { offscreen++; continue; }



    const inViewport = rect.bottom > 0 && rect.top < innerHeight;

    // Перекрытие проверяется только в пределах экрана — elementFromPoint

    // работает в координатах вьюпорта.

    const occ = inViewport ? occlusion(el, rect) : { covered: false };

    if (occ.covered && !landmark) continue;



    const name = accessibleName(el);

    const value = valueOf(el);

    // Безымянный и беззначный элемент агенту бесполезен.

    if (!name && !value && !landmark) continue;



    // «Сильный» — настоящий контрол по тегу или роли, а не по cursor:pointer.

    const strong = INTERACTIVE_TAGS.has(el.tagName)

      || INTERACTIVE_ROLES.has(role)

      || el.isContentEditable;



    const item = {

      ref: refFor(el),

      role: role || el.tagName.toLowerCase(),

      name,

      sig: signature(el, role),

      inViewport,

      top: Math.round(rect.top + scrollY),

    };

    if (value) item.value = value;



    const state = stateOf(el, role);

    if (Object.keys(state).length) item.state = state;



    if (el.tagName === 'A') {

      const href = el.getAttribute('href');

      if (href && !href.startsWith('javascript:')) item.href = href;

    }

    if (landmark) item.landmark = true;



    collected.push({ el, item, strong: strong || landmark });

  }



  const out = dedupeNested(collected).map((c) => c.item);



  // Чистим реестр от узлов, покинувших DOM.

  for (const [ref, el] of registry.byRef) {

    if (!el || !el.isConnected) registry.byRef.delete(ref);

  }



  return {

    url: location.href,

    title: document.title || '',

    elements: out,

    offscreen,

    truncated,

    scroll: {

      y: Math.round(scrollY),

      height: Math.round(document.documentElement.scrollHeight),

      viewport: Math.round(innerHeight),

    },

  };

})();

