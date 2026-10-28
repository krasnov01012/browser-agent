import type { Dict } from './ru';

/*
 * English copy for shared parts and the home page.
 * All drafts (D24). Localised by meaning, not word-for-word from Russian.
 */
export const en: Dict = {
  meta: {
    title: 'Krasnoff Development — Custom Software Engineering Studio',
    description:
      'Independent software studio: web products, business systems, AI and automation, data integrations, infrastructure and support after launch.',
  },
  a11y: {
    skip: 'Skip to content',
    menuOpen: 'Open menu',
    menuClose: 'Close menu',
    langSwitch: 'Переключить на русский',
    home: 'Krasnoff Development — home',
    newTab: 'opens in a new tab',
  },
  nav: {
    work: 'Work',
    services: 'Services',
    about: 'About',
    process: 'Process',
    architect: 'Project brief',
    contact: 'Contact',
    cta: 'Start a project',
    menu: 'Menu',
  },
  hero: {
    eyebrow: 'Custom software engineering',
    titleLines: ['Software.', 'Built', 'for you'],
    lead: 'Custom software, AI and digital products — from concept to launch and ongoing support.',
    ctaPrimary: 'Start a project',
    ctaSecondary: 'Explore work',
    capabilitiesLabel: 'Capabilities',
    kAlt: 'Architectural K — the Krasnoff Development mark: a vertical stem and two diagonal beams with a coral seam at the joint.',
    hud: {
      model: 'K / V02',
      assembly: 'Assembly',
      tilt: 'Tilt',
      fallback: 'Static mark',
    },
    scroll: 'Scroll',
  },
  services: {
    eyebrow: ['02', 'Services'],
    titleLines: ['What', 'we build'],
    lead: 'From a first product to the systems a business runs on. Every engagement is scoped individually — architecture, build, launch and support.',
    deliverablesLabel: 'What it covers',
    cta: 'Discuss this service',
    items: [
      {
        id: 'web',
        title: 'Web & Digital Products',
        short: 'Websites, stores, SaaS, portals',
        description:
          'Websites, online stores, SaaS platforms, customer portals and web applications — designed around how your customers actually use them.',
        deliverables: ['Websites & eCommerce', 'SaaS & web applications', 'Customer portals', 'Content management'],
      },
      {
        id: 'systems',
        title: 'Custom Software & Business Systems',
        short: 'CRM, admin panels, internal tools',
        description:
          'CRM, internal tools, admin panels and bespoke business logic — software shaped around your workflows instead of the other way round.',
        deliverables: ['CRM & internal systems', 'Admin panels', 'Business logic & workflows', 'Custom applications'],
      },
      {
        id: 'ai',
        title: 'AI & Automation',
        short: 'Agents, assistants, LLM integration',
        description:
          'AI agents, assistants and LLM integrations — used where they simplify a real process, with deterministic checks where accuracy matters.',
        deliverables: ['AI agents & assistants', 'LLM integration', 'Workflow automation', 'Document & data processing'],
      },
      {
        id: 'data',
        title: 'Data & Integrations',
        short: 'APIs, ETL, databases, analytics',
        description:
          'APIs, ETL pipelines, databases and dashboards — connecting the services you already use into one reliable flow of data.',
        deliverables: ['API integrations', 'ETL & data pipelines', 'Database design', 'Analytics & dashboards'],
      },
      {
        id: 'infra',
        title: 'Infrastructure & Support',
        short: 'Deploy, hosting, monitoring, care',
        description:
          'Deployment, hosting, domains and TLS, monitoring, backups, updates and further development — a separate paid service after launch, scoped by agreement.',
        deliverables: ['Deployment & hosting', 'Domains & TLS', 'Monitoring & backups', 'Maintenance & development'],
      },
    ],
  },
  bridge: {
    lines: ['Not just ideas.', 'Built systems.'],
  },
  work: {
    eyebrow: ['03', 'Selected work'],
    lead: 'The studio’s own independent products — not client commissions. They show how we engineer whole systems: from data and rules to the interface.',
    independent: 'Independent product',
    explore: 'Explore case',
    seshat: {
      index: '001',
      name: 'Seshat',
      claim: 'Time, engineered.',
      description:
        'A personal planning system: natural-language requests, precise scheduling logic and dependable reminders — in Telegram, on an API-first core.',
      tags: ['Telegram', 'API-first', 'Hybrid NLP', 'PostgreSQL'],
      provenance: 'Illustrative — demo footage pending',
      media: {
        days: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
        message: 'Workout every Monday at 7 pm',
        parsed: 'Routine · weekly · Mon 19:00',
        confirm: 'Confirm',
      },
    },
    mark: {
      index: '002',
      name: 'Mark',
      claim: 'Signal over noise.',
      description:
        'A personal AI job discovery agent: HeadHunter API and Habr Career RSS, explicit rules first, then LLM matching against a private profile — delivered to Telegram.',
      tags: ['HH API', 'Habr RSS', 'Rules', 'LLM', 'Telegram'],
      provenance: 'Conceptual · synthetic — not product UI',
      stages: ['Sources', 'Format', 'Rules', 'AI fit', 'Telegram'],
    },
    lab: {
      index: '003',
      title: 'Engineering Lab',
      note: 'Reserved: future in-house experiments, once publication rights are confirmed.',
    },
  },
  approach: {
    eyebrow: ['04', 'About'],
    titleLines: ['How we', 'engineer'],
    studio:
      'Krasnoff Development is an independent software studio led by its founder. One accountable engineering lead from architecture to launch and support — and business-level clarity at every step.',
    principles: [
      {
        title: 'The business problem first',
        text: 'We start from the process you want to improve, not from a list of technologies. Architecture follows the problem.',
      },
      {
        title: 'AI where it helps',
        text: 'Models interpret language and unstructured data. Critical decisions and calculations stay in deterministic, testable code.',
      },
      {
        title: 'Reliability by design',
        text: 'Validation, idempotency, backups and rollback are designed in from the start — not added after the first incident.',
      },
      {
        title: 'Your product stays yours',
        text: 'Code, access and data are documented and handed over. Support after launch is an option, not a lock-in.',
      },
    ],
  },
  process: {
    eyebrow: ['05', 'Process'],
    titleLines: ['From brief', 'to running', 'system'],
    steps: [
      {
        title: 'Discovery',
        text: 'We clarify goals, users, constraints and existing systems. If the scope is uncertain, we suggest a short discovery phase.',
      },
      {
        title: 'Proposal',
        text: 'An individual proposal: scope, stages, timeline and cost for your particular project. No packages, no generic price list.',
      },
      {
        title: 'Development',
        text: 'Iterative build with regular demos — you see working software early, not only at the end.',
      },
      {
        title: 'Launch',
        text: 'Deployment, data migration, monitoring and handover of code, documentation and access.',
      },
      {
        title: 'Support',
        text: 'Hosting, updates, fixes and further development — a separate paid service, scoped by agreement.',
        optional: 'optional',
      },
    ],
    modelsLabel: 'Ways to work together',
    models: [
      { title: 'Project development', text: 'Turnkey: concept, scope, build, launch and handover.' },
      { title: 'Flexible development', text: 'Integrations, features and work on existing software, by agreed estimates.' },
      { title: 'Managed infrastructure & support', text: 'Administration and evolution of the product after launch.' },
    ],
    pricing:
      'Every project is different. We assess goals, technical requirements, scope and long-term needs — and prepare an individual proposal.',
  },
  architect: {
    eyebrow: ['06', 'Project architect'],
    titleLines: ['Build your', 'project brief'],
    lead: 'Four short steps to describe what you need. Skip anything that doesn’t apply — the result is a structured brief, not a price quote.',
    steps: ['Project type', 'Capabilities', 'Context', 'Summary'],
    stepOf: 'Step',
    next: 'Next',
    back: 'Back',
    skip: 'Skip',
    multiHint: 'Select as many as apply',
    types: [
      { id: 'web', label: 'Web product / SaaS' },
      { id: 'systems', label: 'Custom software' },
      { id: 'ai', label: 'AI / automation' },
      { id: 'data', label: 'Data / integrations' },
      { id: 'infra', label: 'Infrastructure' },
      { id: 'other', label: 'Something else' },
    ],
    otherPlaceholder: 'Describe it in your own words if nothing fits',
    capabilitiesEmpty: 'Pick a project type in step one and relevant capabilities will appear here. Or just describe the task freely.',
    capabilities: {
      web: ['Catalog & online store', 'Online payments', 'User accounts', 'Content management', 'Multilingual', 'Third-party integrations'],
      systems: ['CRM / client base', 'Admin panel', 'Roles & permissions', 'Reports & documents', 'Workflow automation', 'Mobile access'],
      ai: ['Assistant / chatbot', 'Document processing', 'Data extraction', 'Classification & routing', 'Human review step', 'Knowledge base search'],
      data: ['API integrations', 'Sync between services', 'ETL / data pipeline', 'Dashboards & analytics', 'Database design', 'Import & migration'],
      infra: ['Deployment & hosting', 'Domains & TLS', 'Monitoring & alerts', 'Backups', 'Updates & maintenance', 'Server migration'],
      other: [] as string[],
    },
    capabilitiesNote: 'Anything else that matters?',
    context: {
      stageLabel: 'Stage',
      stages: ['New idea', 'Existing product', 'Scaling up'],
      materialsLabel: 'What you already have',
      materials: ['Brief / spec', 'Design', 'Nothing yet'],
      timingLabel: 'Timing',
      timings: ['No fixed deadline', 'As soon as possible', 'By a specific date'],
      supportLabel: 'Support after launch',
      supports: ['Needed', 'Not sure yet', 'Not needed'],
      notesPlaceholder: 'Notes: deadlines, constraints, links to materials…',
    },
    summary: {
      title: 'Summary',
      hint: 'Review and edit the text if needed — it will be sent with your request.',
      empty: 'Nothing selected yet — describe the task in your own words.',
      headings: { type: 'Type', capabilities: 'Capabilities', stage: 'Stage', materials: 'Has', timing: 'Timing', support: 'Support', notes: 'Notes' },
    },
  },
  contact: {
    modes: { quick: 'Quick inquiry', brief: 'Project brief' },
    eyebrow: ['06', 'Contact'],
    titleLines: ['Have an idea?', 'Let’s build it.'],
    lead: 'Tell us about the task in a few sentences and choose how you’d like a reply — Telegram or email. No calls required.',
    next: 'What happens next: we review the request and reply via your chosen channel, with clarifying questions if needed.',
    noPrice: 'No public pricing: every proposal is prepared for the specific project.',
    form: {
      name: 'Your name',
      namePlaceholder: 'Name',
      channel: 'Reply via',
      telegram: 'Telegram',
      email: 'Email',
      contactTelegram: 'Your Telegram',
      contactTelegramPlaceholder: '@username',
      contactEmail: 'Your email',
      contactEmailPlaceholder: 'name@company.com',
      message: 'About the project',
      messagePlaceholder: 'What needs to be built, for whom, and what exists already',
      context: 'Context',
      removeContext: 'Remove context',
      consent: 'I agree to the processing of the data I submit in order to receive a reply.',
      privacy: 'Privacy policy',
      submit: 'Send inquiry',
      sending: 'Sending…',
      required: 'required',
    },
    errors: {
      name: 'Please tell us how to address you.',
      telegram: 'Enter a Telegram handle like @username (5–32 characters: latin letters, digits, _).',
      email: 'Enter a valid email address.',
      message: 'Please describe the task in a couple of sentences (20+ characters).',
      consent: 'We need your consent to process the data in order to reply.',
      summary: 'Please check the highlighted fields.',
    },
    states: {
      success: 'Request received and stored. We’ll reply via your chosen channel.',
      telegramNote:
        'A bot can’t message you first from a @username alone. Once the studio bot is connected, a button to open the conversation will appear here.',
      error: 'Couldn’t send the request. Your text is still in the form — please try again a little later.',
      notConfigured:
        'Preview build: request intake is not connected yet, nothing was sent. Your text is still in the form.',
    },
  },
  footer: {
    tagline: 'Custom software, AI and digital products — from concept to launch and ongoing support.',
    navTitle: 'Navigation',
    workTitle: 'Work',
    langTitle: 'Language',
    legalTitle: 'Legal',
    privacy: 'Privacy policy',
    rights: 'Krasnoff Development',
    build: 'Build',
    top: 'Back to top',
  },
  privacy: {
    title: 'Privacy policy',
    draft:
      'Draft placeholder. The policy is being prepared for the actual data controller and jurisdiction and will be published after legal review.',
  },
  notFound: {
    title: 'Page not found',
    text: 'The link may be outdated. Head back to the home page — everything is reachable from there.',
    back: 'Back home',
  },
  review: {
    on: 'Review mode',
    legend: 'Status marks: draft — copy draft, proposed — design proposal, placeholder — slot for real material, reserved — held for later.',
  },
};
