export const SUPPORTED_LANGUAGES = ["en", "hi", "bn"] as const;
export type Language = (typeof SUPPORTED_LANGUAGES)[number];
export const LANGUAGE_VALUES = [...SUPPORTED_LANGUAGES] as [Language, ...Language[]];

type UiStrings = {
  siteTitle: string;
  siteDescription: string;
  tagline: string;
  aiDisclosure: string;
  mainNavigation: string;
  home: string;
  allTopics: string;
  chooseLanguage: string;
  useLightTheme: string;
  useDarkTheme: string;
  chooseTopic: string;
  topicPrompt: string;
  topics: string;
  latest: string;
  newestLesson: string;
  startHere: string;
  moreLessons: string;
  chooseAnother: string;
  readLesson: string;
  allLessons: string;
  latestLessons: string;
  topic: string;
  updated: string;
  published: string;
  remember: string;
  gentleNote: string;
  otherLessons: string;
  previousLesson: string;
  nextLesson: string;
  shareLesson: string;
  linkCopied: string;
  lessonsPageTitle: string;
  learnAtYourPace: string;
  pageOf: string;
  pagination: string;
  previous: string;
  next: string;
};

type Locale = {
  name: string;
  dateLocale: string;
  ui: UiStrings;
};

export const LOCALES: Record<Language, Locale> = {
  en: {
    name: "English",
    dateLocale: "en",
    ui: {
      siteTitle: "Saral — AI made simple, so no one is left behind",
      siteDescription: "Clear, useful technology lessons for everyday life.",
      tagline: "AI made simple, so no one is left behind.",
      aiDisclosure: "All lessons, translations, and illustrations on this website are generated using AI.",
      mainNavigation: "Main navigation",
      home: "Home",
      allTopics: "All topics",
      chooseLanguage: "Choose language",
      useLightTheme: "Use light theme",
      useDarkTheme: "Use dark theme",
      chooseTopic: "Choose a topic",
      topicPrompt: "What would you like help with?",
      topics: "Topics",
      latest: "Latest",
      newestLesson: "Newest lesson",
      startHere: "Start here",
      moreLessons: "More lessons",
      chooseAnother: "Choose another",
      readLesson: "Read this lesson",
      allLessons: "All lessons",
      latestLessons: "Latest lessons",
      topic: "Topic",
      updated: "Updated",
      published: "Published",
      remember: "Remember",
      gentleNote: "It is okay to learn one step at a time. Take a pause whenever you need one.",
      otherLessons: "Other lessons",
      previousLesson: "Previous lesson",
      nextLesson: "Next lesson",
      shareLesson: "Share this lesson",
      linkCopied: "Link copied",
      lessonsPageTitle: "Lessons",
      learnAtYourPace: "Learn at your pace.",
      pageOf: "Page {page} of {count}",
      pagination: "Pagination",
      previous: "Previous",
      next: "Next",
    },
  },
  hi: {
    name: "हिन्दी",
    dateLocale: "hi-IN",
    ui: {
      siteTitle: "सरल — एआई आसान भाषा में, ताकि कोई पीछे न छूटे",
      siteDescription: "रोज़मर्रा की ज़िंदगी के लिए साफ़ और उपयोगी तकनीकी पाठ।",
      tagline: "एआई आसान भाषा में, ताकि कोई पीछे न छूटे।",
      aiDisclosure: "इस वेबसाइट के सभी पाठ, अनुवाद और चित्र एआई का उपयोग करके बनाए गए हैं।",
      mainNavigation: "मुख्य नेविगेशन",
      home: "मुख्य पृष्ठ",
      allTopics: "सभी विषय",
      chooseLanguage: "भाषा चुनें",
      useLightTheme: "हल्की थीम इस्तेमाल करें",
      useDarkTheme: "गहरी थीम इस्तेमाल करें",
      chooseTopic: "विषय चुनें",
      topicPrompt: "आप किस बारे में सीखना चाहते हैं?",
      topics: "विषय",
      latest: "नवीनतम",
      newestLesson: "नया पाठ",
      startHere: "यहाँ से शुरू करें",
      moreLessons: "और पाठ",
      chooseAnother: "कोई और चुनें",
      readLesson: "यह पाठ पढ़ें",
      allLessons: "सभी पाठ",
      latestLessons: "नवीनतम पाठ",
      topic: "विषय",
      updated: "अपडेट किया गया",
      published: "प्रकाशित",
      remember: "याद रखें",
      gentleNote: "आप एक समय में एक कदम सीख सकते हैं।",
      otherLessons: "अन्य पाठ",
      previousLesson: "पिछला पाठ",
      nextLesson: "अगला पाठ",
      shareLesson: "यह पाठ साझा करें",
      linkCopied: "लिंक कॉपी हो गया",
      lessonsPageTitle: "पाठ",
      learnAtYourPace: "अपनी गति से सीखें।",
      pageOf: "पृष्ठ {page} / {count}",
      pagination: "पृष्ठ नेविगेशन",
      previous: "पिछला",
      next: "अगला",
    },
  },
  bn: {
    name: "বাংলা",
    dateLocale: "bn-BD",
    ui: {
      siteTitle: "সরল — সহজ ভাষায় এআই, যাতে কেউ পিছিয়ে না থাকে",
      siteDescription: "প্রতিদিনের জীবনের জন্য পরিষ্কার ও উপকারী প্রযুক্তি পাঠ।",
      tagline: "সহজ ভাষায় এআই, যাতে কেউ পিছিয়ে না থাকে।",
      aiDisclosure: "এই ওয়েবসাইটের সব পাঠ, অনুবাদ ও ছবি এআই ব্যবহার করে তৈরি করা হয়েছে।",
      mainNavigation: "মূল নেভিগেশন",
      home: "মূল পাতা",
      allTopics: "সব বিষয়",
      chooseLanguage: "ভাষা বেছে নিন",
      useLightTheme: "হালকা থিম ব্যবহার করুন",
      useDarkTheme: "গাঢ় থিম ব্যবহার করুন",
      chooseTopic: "বিষয় বেছে নিন",
      topicPrompt: "আপনি কী বিষয়ে সাহায্য চান?",
      topics: "বিষয়",
      latest: "সাম্প্রতিক",
      newestLesson: "নতুন পাঠ",
      startHere: "এখান থেকে শুরু করুন",
      moreLessons: "আরও পাঠ",
      chooseAnother: "আরেকটি বেছে নিন",
      readLesson: "এই পাঠটি পড়ুন",
      allLessons: "সব পাঠ",
      latestLessons: "সাম্প্রতিক পাঠ",
      topic: "বিষয়",
      updated: "আপডেট করা হয়েছে",
      published: "প্রকাশিত",
      remember: "মনে রাখবেন",
      gentleNote: "আপনি একবারে এক ধাপ শিখতে পারেন।",
      otherLessons: "অন্যান্য পাঠ",
      previousLesson: "আগের পাঠ",
      nextLesson: "পরের পাঠ",
      shareLesson: "এই পাঠটি শেয়ার করুন",
      linkCopied: "লিঙ্ক কপি হয়েছে",
      lessonsPageTitle: "পাঠ",
      learnAtYourPace: "নিজের গতিতে শিখুন।",
      pageOf: "পৃষ্ঠা {page} / {count}",
      pagination: "পৃষ্ঠা নেভিগেশন",
      previous: "আগের",
      next: "পরের",
    },
  },
};

export function locale(language: Language) {
  return LOCALES[language];
}

export function ui(language: Language) {
  return LOCALES[language].ui;
}

export function format(template: string, values: Record<string, string | number>) {
  return template.replace(/\{(\w+)\}/g, (_, key: string) => String(values[key] ?? `{${key}}`));
}
