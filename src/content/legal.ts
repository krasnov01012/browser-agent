/*
 * Юридические страницы: политика обработки персональных данных и согласие.
 * ЧЕРНОВИК-ШАБЛОН под схему «форма → релей без хранения → Telegram администратора» (docs/LEGAL_GUIDE.md).
 * Поля в квадратных скобках [[…]] — данные оператора, которые вносит владелец. До юридической проверки
 * страницы закрыты от индексации и помечены как черновик. Это не юридическая консультация.
 */
export interface LegalSection {
  h: string;
  p: string[];
}

export interface LegalDoc {
  title: string;
  banner: string;
  updated: string;
  sections: LegalSection[];
}

const OPERATOR_RU = '[[ФИО индивидуального предпринимателя / самозанятого или наименование ООО]], ИНН [[…]], адрес: [[…]]';
const OPERATOR_EN = '[[full name of sole proprietor or company name]], tax ID [[…]], address: [[…]]';

export const policy: Record<'ru' | 'en', LegalDoc> = {
  ru: {
    title: 'Политика обработки персональных данных',
    banner: 'Черновик. Поля в [[двойных скобках]] заполняются данными оператора; текст проходит юридическую проверку до публикации.',
    updated: 'Редакция от [[дата публикации]]',
    sections: [
      {
        h: '1. Общие положения',
        p: [
          'Политика описывает, какие персональные данные мы получаем через сайт Krasnoff Development, зачем, как их защищаем и как вы можете повлиять на их обработку. Она подготовлена в соответствии с Федеральным законом № 152-ФЗ «О персональных данных».',
          `Оператор персональных данных: ${OPERATOR_RU}. Контакт по вопросам данных: [[email для обращений]].`,
        ],
      },
      {
        h: '2. Какие данные мы обрабатываем',
        p: [
          'Только те, что вы сами указываете в форме заявки или брифа: имя, контакт для ответа (Telegram @username или email), текст описания задачи, ответы в брифе проекта. Мы не просим паспортные данные, адрес, телефон, данные карт и иные сведения, которые не нужны для ответа.',
          'Технические данные: сервер сайта может фиксировать IP-адрес, время и адрес запрошенной страницы в техническом журнале [[срок хранения журнала, например 14 дней]] — для защиты от злоупотреблений и диагностики. Аналитические и рекламные счётчики на сайте не используются.',
        ],
      },
      {
        h: '3. Цели и основания обработки',
        p: [
          'Цель — ответить на ваш запрос и, если вы этого захотите, подготовить предложение по проекту. Основания: ваше согласие (п. 1 ч. 1 ст. 6 152-ФЗ) и принятие мер по вашему запросу до заключения договора (п. 5 ч. 1 ст. 6).',
          'Мы не используем данные для рассылок и не передаём их для рекламы.',
        ],
      },
      {
        h: '4. Как данные проходят через сайт',
        p: [
          'Заявка отправляется с сайта на технический сервер приёма, который не записывает её на диск и не ведёт базу заявок: он сразу пересылает сообщение администратору студии через сервис Telegram и забывает его. В технических журналах приёма хранятся только счётчики, без имён, контактов и текстов.',
          'Дальше заявка существует в переписке администратора в Telegram и, если вы решите работать с нами, в рабочих материалах проекта. [[Укажите, где ведётся учёт обращений: например, локальная таблица на устройстве в РФ.]]',
        ],
      },
      {
        h: '5. Передача третьим лицам и за границу',
        p: [
          'Для доставки заявки используется Telegram (оператор — Telegram FZ-LLC; серверы сервиса расположены за пределами РФ). Таким образом, ваши данные передаются на территорию иностранных государств. Мы уведомили [[или: уведомим до начала передачи]] Роскомнадзор о трансграничной передаче в соответствии со ст. 12 152-ФЗ. [[Проверить актуальный статус и страны получателя]].',
          'Если вы выбрали ответ по email, письма проходят через почтовых провайдеров, которые вы и мы используем. Иным третьим лицам данные не передаются, кроме случаев, прямо предусмотренных законом.',
        ],
      },
      {
        h: '6. Сроки хранения и удаление',
        p: [
          'Заявки, по которым не началась работа, удаляются из переписки в течение [[N]] месяцев после ответа. Если вы стали клиентом, данные хранятся в течение срока договора и срока, необходимого по закону. По вашему запросу мы удалим данные раньше (см. раздел 7).',
        ],
      },
      {
        h: '7. Ваши права',
        p: [
          'Вы вправе: получить сведения об обработке своих данных, потребовать их уточнения, блокирования или удаления, отозвать согласие, возразить против обработки. Для этого напишите на [[email для обращений]] с указанием имени и контакта, который вы использовали в заявке.',
          'Мы ответим в срок, установленный законом (на сегодня — до 10 рабочих дней с возможным продлением). Согласие можно отозвать в любой момент тем же способом. Вы также вправе обратиться с жалобой в Роскомнадзор (rkn.gov.ru) или в суд.',
        ],
      },
      {
        h: '8. Меры защиты',
        p: [
          'Передача данных с сайта защищена шифрованием (HTTPS). Сервер приёма не хранит заявки, доступ к нему ограничен, токены доступа не публикуются. Доступ к заявкам имеет только оператор. В случае инцидента мы уведомим Роскомнадзор и пострадавших в порядке, предусмотренном законом.',
        ],
      },
      {
        h: '9. Cookie и локальное хранилище',
        p: ['Сайт не использует аналитические и рекламные cookie. Могут использоваться технически необходимые данные браузера (например, запоминание выбранного языка) — они не содержат персональных данных.'],
      },
      {
        h: '10. Изменения политики',
        p: ['Актуальная редакция всегда доступна по этому адресу. При существенных изменениях мы обновим дату редакции.'],
      },
    ],
  },
  en: {
    title: 'Privacy policy',
    banner: 'Draft. Fields in [[double brackets]] are filled with the operator’s details; the text goes through legal review before publication.',
    updated: 'Version of [[publication date]]',
    sections: [
      {
        h: '1. General',
        p: [
          'This policy explains what personal data we receive through the Krasnoff Development website, why, how we protect it and how you can control it. It is drawn up under Russian Federal Law No. 152-FZ “On Personal Data” and, for visitors in the EU/EEA, with the GDPR principles in mind.',
          `Data controller: ${OPERATOR_EN}. Data contact: [[email for requests]].`,
        ],
      },
      {
        h: '2. Data we process',
        p: [
          'Only what you enter in the inquiry or brief form: name, a contact for the reply (Telegram @username or email), the task description and your brief answers. We do not ask for ID numbers, addresses, phone numbers, payment data or anything not needed to reply.',
          'Technical data: the web server may log IP address, time and requested page for [[log retention, e.g. 14 days]] for abuse protection and diagnostics. The site uses no analytics or advertising trackers.',
        ],
      },
      {
        h: '3. Purposes and legal bases',
        p: [
          'Purpose: to reply to your inquiry and, if you wish, prepare a project proposal. Legal bases: your consent and steps taken at your request before entering into a contract (Art. 6(1)(a) and (b) GDPR; Art. 6 of 152-FZ).',
          'We do not use your data for mailing lists and do not pass it on for advertising.',
        ],
      },
      {
        h: '4. How your data moves through the site',
        p: [
          'The inquiry is sent to a technical intake server that does not write it to disk and keeps no database of inquiries: it immediately forwards the message to the studio administrator via Telegram and forgets it. Intake logs keep counters only — no names, contacts or texts.',
          'After that the inquiry exists in the administrator’s Telegram conversation and, if we work together, in project materials. [[State where inquiries are tracked.]]',
        ],
      },
      {
        h: '5. Third parties and international transfers',
        p: [
          'Delivery uses Telegram (operated by Telegram FZ-LLC; its servers are located outside Russia), so your data is transferred to other countries. [[Describe the notification status and recipient countries after verification.]]',
          'If you choose email, messages pass through the mail providers you and we use. We do not share data with anyone else unless the law requires it.',
        ],
      },
      {
        h: '6. Retention and deletion',
        p: ['Inquiries that do not lead to work are deleted from the conversation within [[N]] months after the reply. If you become a client, data is kept for the term of the contract and the period required by law. You can ask for earlier deletion (section 7).'],
      },
      {
        h: '7. Your rights',
        p: [
          'You may request information about the processing of your data, correction, blocking or deletion, withdraw consent or object to processing. Write to [[email for requests]] with your name and the contact you used in the inquiry.',
          'We reply within the period set by law (currently up to 10 working days, extendable). You may also complain to the Russian regulator (Roskomnadzor), your local data protection authority or a court.',
        ],
      },
      {
        h: '8. Security',
        p: ['Data sent from the site is encrypted (HTTPS). The intake server does not store inquiries, access to it is restricted and access tokens are never published. Only the operator can read inquiries. In case of an incident we will notify the regulator and affected people as required by law.'],
      },
      {
        h: '9. Cookies and local storage',
        p: ['The site uses no analytics or advertising cookies. It may use technically necessary browser storage (for example, remembering your language) that contains no personal data.'],
      },
      {
        h: '10. Changes',
        p: ['The current version is always available at this address. We update the date when the policy changes materially.'],
      },
    ],
  },
};

export const consent: Record<'ru' | 'en', LegalDoc> = {
  ru: {
    title: 'Согласие на обработку персональных данных',
    banner: 'Черновик. Оформлено отдельным документом, как того требует закон; проходит юридическую проверку.',
    updated: 'Редакция от [[дата публикации]]',
    sections: [
      {
        h: 'Согласие',
        p: [
          `Я, отправляя форму на сайте Krasnoff Development, свободно, своей волей и в своём интересе даю согласие оператору — ${OPERATOR_RU} — на обработку моих персональных данных.`,
          'Состав данных: имя, Telegram @username или email, текст заявки и ответы брифа проекта, добровольно указанные мной.',
          'Цель: получить ответ на запрос и подготовить предложение по проекту.',
          'Действия с данными: сбор, запись, передача (предоставление) через сервис Telegram, хранение в переписке оператора, удаление. Обработка автоматизированная с использованием средств Telegram.',
          'Трансграничная передача: я понимаю, что при передаче через Telegram данные могут обрабатываться на серверах за пределами Российской Федерации.',
          'Срок: до достижения цели, но не дольше [[N]] месяцев, если договор не заключён; согласие действует до его отзыва.',
          'Отзыв: согласие можно отозвать в любой момент, написав на [[email для обращений]]; оператор прекратит обработку и удалит данные в установленный законом срок.',
        ],
      },
    ],
  },
  en: {
    title: 'Consent to personal data processing',
    banner: 'Draft. Provided as a separate document, as the law requires; goes through legal review.',
    updated: 'Version of [[publication date]]',
    sections: [
      {
        h: 'Consent',
        p: [
          `By submitting the form on the Krasnoff Development website I freely and in my own interest consent to the controller — ${OPERATOR_EN} — processing my personal data.`,
          'Data: name, Telegram @username or email, inquiry text and brief answers that I provide voluntarily.',
          'Purpose: to receive a reply to my request and a project proposal.',
          'Operations: collection, recording, transfer via the Telegram service, storage in the controller’s conversation, deletion. Processing is automated using Telegram tools.',
          'International transfer: I understand that data sent via Telegram may be processed on servers outside the Russian Federation.',
          'Term: until the purpose is achieved, no longer than [[N]] months if no contract is concluded; consent remains valid until withdrawn.',
          'Withdrawal: I can withdraw consent at any time by writing to [[email for requests]]; the controller will stop processing and delete the data within the statutory period.',
        ],
      },
    ],
  },
};
