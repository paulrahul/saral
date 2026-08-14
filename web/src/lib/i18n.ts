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
  aboutSaral: string;
  aboutPageTitle: string;
  aboutPageDescription: string;
  aboutIntro: string;
  aboutGoalHeading: string;
  aboutGoalOne: string;
  aboutGoalTwo: string;
  aboutGoalThree: string;
  aboutGoalFour: string;
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
  aiProductionCost: string;
  viewCostBreakdown: string;
  costDataUnavailable: string;
  aiProductionCosts: string;
  costTransparencyIntro: string;
  averageRecordedCost: string;
  exploreCostDetails: string;
  costDataUnavailableShort: string;
  costOverview: string;
  totalRecordedCost: string;
  generationTime: string;
  modelCalls: string;
  costByStage: string;
  modelsUsed: string;
  stage: string;
  models: string;
  calls: string;
  cost: string;
  shareOfCost: string;
  model: string;
  provider: string;
  inputTokens: string;
  outputTokens: string;
  partialCostNote: string;
  seconds: string;
  minutes: string;
  contentGeneration: string;
  contentEvaluation: string;
  tagGeneration: string;
  tagEvaluation: string;
  imageGeneration: string;
  bengaliTranslation: string;
  hindiTranslation: string;
  markdownRebuild: string;
  backToTop: string;
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
      siteTitle: "Saral — Technology made simple, so no one is left behind",
      siteDescription: "Clear, useful technology lessons for everyday life.",
      tagline: "Technology made simple, so no one is left behind.",
      aiDisclosure: "All lessons, translations, and illustrations on this website are generated using AI.",
      mainNavigation: "Main navigation",
      home: "Home",
      allTopics: "All topics",
      aboutSaral: "About Saral",
      aboutPageTitle: "About Saral",
      aboutPageDescription: "Saral makes everyday technology easier to understand, so no one is left behind.",
      aboutIntro: "Saral is here to make technology feel less difficult and more useful in everyday life.",
      aboutGoalHeading: "Our goal",
      aboutGoalOne: "Help older adults, people with limited resources, and others who have been left out of technology learn the basics.",
      aboutGoalTwo: "Explain emerging technology in very simple, clear language — without assuming prior knowledge.",
      aboutGoalThree: "Build confidence with everyday tasks such as using the AI, internet, smartphones, messaging apps, websites, online orders, and Google.",
      aboutGoalFour: "Make sure marginalised communities are not left behind by technologies that affect society and personal life.",
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
      aiProductionCost: "AI production cost: {cost}",
      viewCostBreakdown: "View cost breakdown",
      costDataUnavailable: "AI production cost: Data not available",
      aiProductionCosts: "AI production costs",
      costTransparencyIntro: "See the latest recorded costs, models, and token usage for each Saral lesson.",
      averageRecordedCost: "Average AI production cost: {cost} per article ·",
      exploreCostDetails: "Explore cost details",
      costDataUnavailableShort: "Data not available",
      costOverview: "Cost overview",
      totalRecordedCost: "Total recorded cost",
      generationTime: "Generation time",
      modelCalls: "Model calls",
      costByStage: "Cost by stage",
      modelsUsed: "Models used",
      stage: "Stage",
      models: "Models",
      calls: "Calls",
      cost: "Cost",
      shareOfCost: "Share",
      model: "Model",
      provider: "Provider",
      inputTokens: "Input tokens",
      outputTokens: "Output tokens",
      partialCostNote: "Some provider cost data was unavailable. The total shown is a known minimum.",
      seconds: "sec",
      minutes: "min",
      contentGeneration: "Content generation",
      contentEvaluation: "Content evaluation",
      tagGeneration: "Tag generation",
      tagEvaluation: "Tag evaluation",
      imageGeneration: "Image generation",
      bengaliTranslation: "Bengali translation",
      hindiTranslation: "Hindi translation",
      markdownRebuild: "Markdown rebuild",
      backToTop: "Back to top",
    },
  },
  hi: {
    name: "हिन्दी",
    dateLocale: "hi-IN-u-nu-deva",
    ui: {
      siteTitle: "सरल — तकनीकी आसान भाषा में, ताकि कोई पीछे न छूटे",
      siteDescription: "रोज़मर्रा की ज़िंदगी के लिए साफ़ और उपयोगी तकनीकी पाठ।",
      tagline: "तकनीकी आसान भाषा में, ताकि कोई पीछे न छूटे।",
      aiDisclosure: "इस वेबसाइट के सभी पाठ, अनुवाद और चित्र एआई का उपयोग करके बनाए गए हैं।",
      mainNavigation: "मुख्य नेविगेशन",
      home: "मुख्य पृष्ठ",
      allTopics: "सभी विषय",
      aboutSaral: "सरल के बारे में",
      aboutPageTitle: "सरल के बारे में",
      aboutPageDescription: "सरल रोज़मर्रा की तकनीक को समझना आसान बनाता है, ताकि कोई पीछे न छूटे।",
      aboutIntro: "सरल का उद्देश्य तकनीक को कम कठिन और रोज़मर्रा की ज़िंदगी में ज़्यादा उपयोगी बनाना है।",
      aboutGoalHeading: "हमारा लक्ष्य",
      aboutGoalOne: "बुज़ुर्गों, सीमित संसाधनों वाले लोगों और उन लोगों को बुनियादी बातें सीखने में मदद करना जो तकनीक से पीछे रह गए हैं।",
      aboutGoalTwo: "नई तकनीकों को बहुत सरल और साफ़ भाषा में समझाना — बिना यह माने कि आपको पहले से कुछ पता है।",
      aboutGoalThree: "एआई, इंटरनेट, स्मार्टफ़ोन, मैसेजिंग ऐप, वेबसाइट, ऑनलाइन ऑर्डर और गूगल जैसे रोज़मर्रा के कामों के लिए आत्मविश्वास बढ़ाना।",
      aboutGoalFour: "यह सुनिश्चित करना कि समाज और निजी जीवन को प्रभावित करने वाली तकनीकों में हाशिए पर रहने वाले समुदाय पीछे न छूटें।",
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
      aiProductionCost: "एआई निर्माण लागत: {cost}",
      viewCostBreakdown: "लागत का विवरण देखें",
      costDataUnavailable: "एआई निर्माण लागत: डेटा उपलब्ध नहीं है",
      aiProductionCosts: "एआई निर्माण लागत",
      costTransparencyIntro: "सरल के हर पाठ के लिए नवीनतम दर्ज लागत, मॉडल और टोकन उपयोग देखें।",
      averageRecordedCost: "औसत एआई निर्माण लागत: {cost} प्रति पाठ ·",
      exploreCostDetails: "लागत विवरण देखें",
      costDataUnavailableShort: "डेटा उपलब्ध नहीं है",
      costOverview: "लागत का सार",
      totalRecordedCost: "कुल दर्ज लागत",
      generationTime: "निर्माण समय",
      modelCalls: "मॉडल कॉल",
      costByStage: "चरण के अनुसार लागत",
      modelsUsed: "इस्तेमाल किए गए मॉडल",
      stage: "चरण",
      models: "मॉडल",
      calls: "कॉल",
      cost: "लागत",
      shareOfCost: "हिस्सा",
      model: "मॉडल",
      provider: "प्रदाता",
      inputTokens: "इनपुट टोकन",
      outputTokens: "आउटपुट टोकन",
      partialCostNote: "कुछ प्रदाताओं की लागत का डेटा उपलब्ध नहीं था। दिखाई गई कुल लागत ज्ञात न्यूनतम है।",
      seconds: "सेकंड",
      minutes: "मिनट",
      contentGeneration: "सामग्री निर्माण",
      contentEvaluation: "सामग्री मूल्यांकन",
      tagGeneration: "टैग निर्माण",
      tagEvaluation: "टैग मूल्यांकन",
      imageGeneration: "चित्र निर्माण",
      bengaliTranslation: "बांग्ला अनुवाद",
      hindiTranslation: "हिन्दी अनुवाद",
      markdownRebuild: "मार्कडाउन पुनर्निर्माण",
      backToTop: "ऊपर जाएँ",
    },
  },
  bn: {
    name: "বাংলা",
    dateLocale: "bn-BD",
    ui: {
      siteTitle: "সরল — সহজ ভাষায় প্রযুক্তি, যাতে কেউ পিছিয়ে না থাকে",
      siteDescription: "প্রতিদিনের জীবনের জন্য পরিষ্কার ও উপকারী প্রযুক্তি পাঠ।",
      tagline: "সহজ ভাষায় প্রযুক্তি, যাতে কেউ পিছিয়ে না থাকে।",
      aiDisclosure: "এই ওয়েবসাইটের সব পাঠ, অনুবাদ ও ছবি এআই ব্যবহার করে তৈরি করা হয়েছে।",
      mainNavigation: "মূল নেভিগেশন",
      home: "মূল পাতা",
      allTopics: "সব বিষয়",
      aboutSaral: "সরল সম্পর্কে",
      aboutPageTitle: "সরল সম্পর্কে",
      aboutPageDescription: "সরল দৈনন্দিন প্রযুক্তি বোঝা সহজ করে, যাতে কেউ পিছিয়ে না থাকে।",
      aboutIntro: "সরল প্রযুক্তিকে কম কঠিন এবং দৈনন্দিন জীবনে আরও কাজে লাগার মতো করে তুলতে চায়।",
      aboutGoalHeading: "আমাদের লক্ষ্য",
      aboutGoalOne: "বয়স্ক মানুষ, সীমিত সম্পদের মানুষ এবং প্রযুক্তি থেকে পিছিয়ে পড়া অন্যদের মৌলিক বিষয় শিখতে সাহায্য করা।",
      aboutGoalTwo: "আগে থেকে কিছু জানা আছে ধরে না নিয়ে, নতুন প্রযুক্তি খুব সহজ ও পরিষ্কার ভাষায় ব্যাখ্যা করা।",
      aboutGoalThree: "এআই, ইন্টারনেট, স্মার্টফোন, মেসেজিং অ্যাপ, ওয়েবসাইট, অনলাইন অর্ডার ও গুগলের মতো দৈনন্দিন কাজের জন্য আত্মবিশ্বাস তৈরি করা।",
      aboutGoalFour: "সমাজ ও ব্যক্তিগত জীবনে প্রভাব ফেলা প্রযুক্তিগুলোতে প্রান্তিক জনগোষ্ঠী যেন পিছিয়ে না পড়ে, তা নিশ্চিত করা।",
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
      aiProductionCost: "এআই তৈরির খরচ: {cost}",
      viewCostBreakdown: "খরচের বিবরণ দেখুন",
      costDataUnavailable: "এআই তৈরির খরচ: তথ্য উপলভ্য নয়",
      aiProductionCosts: "এআই তৈরির খরচ",
      costTransparencyIntro: "সরলের প্রতিটি পাঠের সর্বশেষ নথিভুক্ত খরচ, মডেল এবং টোকেন ব্যবহার দেখুন।",
      averageRecordedCost: "গড় এআই তৈরির খরচ: প্রতি পাঠে {cost} ·",
      exploreCostDetails: "খরচের বিবরণ দেখুন",
      costDataUnavailableShort: "তথ্য উপলভ্য নয়",
      costOverview: "খরচের সারাংশ",
      totalRecordedCost: "মোট নথিভুক্ত খরচ",
      generationTime: "তৈরির সময়",
      modelCalls: "মডেল কল",
      costByStage: "ধাপ অনুযায়ী খরচ",
      modelsUsed: "ব্যবহৃত মডেল",
      stage: "ধাপ",
      models: "মডেল",
      calls: "কল",
      cost: "খরচ",
      shareOfCost: "অংশ",
      model: "মডেল",
      provider: "প্রদানকারী",
      inputTokens: "ইনপুট টোকেন",
      outputTokens: "আউটপুট টোকেন",
      partialCostNote: "কিছু প্রদানকারীর খরচের তথ্য পাওয়া যায়নি। দেখানো মোটটি জানা ন্যূনতম পরিমাণ।",
      seconds: "সেকেন্ড",
      minutes: "মিনিট",
      contentGeneration: "বিষয়বস্তু তৈরি",
      contentEvaluation: "বিষয়বস্তু মূল্যায়ন",
      tagGeneration: "ট্যাগ তৈরি",
      tagEvaluation: "ট্যাগ মূল্যায়ন",
      imageGeneration: "ছবি তৈরি",
      bengaliTranslation: "বাংলা অনুবাদ",
      hindiTranslation: "হিন্দি অনুবাদ",
      markdownRebuild: "মার্কডাউন পুনর্গঠন",
      backToTop: "উপরে যান",
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
