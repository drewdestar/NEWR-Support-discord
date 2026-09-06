/**
 * Multilanguage Handler - 25+ Languages
 * Professional Grade Internationalization System
 * 
 * ────────────────────────────────────────────────────────
 * © COPYRIGHT NEWROPLY - ALL RIGHTS RESERVED
 * Developed by NEWR LABS
 * 
 * NEWROPLY is the parent company (like Meta)
 * NEWR LABS is the development studio/brand (like Instagram under Meta)
 * ────────────────────────────────────────────────────────
 * 
 * Author: NEWR LABS Localization Team
 * Company: NEWROPLY
 * License: Proprietary - NEWROPLY
 * 
 * ⚠️ This language system is property of NEWROPLY.
 * Unauthorized use is strictly prohibited.
 * ────────────────────────────────────────────────────────
 */

class LanguageHandler {
    constructor() {
        console.log('🌍 Language Handler initialized - Powered by NEWR LABS');
        console.log('© 2024 NEWROPLY - All Rights Reserved');
        
        this.languages = {
            id: require('../languages/id'),
            en: require('../languages/en'),
            es: require('../languages/es'),
            fr: require('../languages/fr'),
            de: require('../languages/de'),
            pt: require('../languages/pt'),
            ru: require('../languages/ru'),
            ja: require('../languages/ja'),
            ko: require('../languages/ko'),
            zh: require('../languages/zh'),
            ar: require('../languages/ar'),
            tr: require('../languages/tr'),
            it: require('../languages/it'),
            nl: require('../languages/nl'),
            pl: require('../languages/pl'),
            vi: require('../languages/vi'),
            th: require('../languages/th'),
            hi: require('../languages/hi'),
            uk: require('../languages/uk'),
            ro: require('../languages/ro'),
            sv: require('../languages/sv'),
            no: require('../languages/no'),
            da: require('../languages/da'),
            fi: require('../languages/fi'),
            cs: require('../languages/cs')
        };
        this.defaultLang = 'id';
    }

    get(lang, key, replacements = {}) {
        const language = this.languages[lang] || this.languages[this.defaultLang];
        let text = this.getNestedValue(language, key) || this.getNestedValue(this.languages.en, key) || key;
        
        for (const [key, value] of Object.entries(replacements)) {
            text = text.replace(new RegExp(`{${key}}`, 'g'), value);
        }
        
        return text;
    }

    getNestedValue(obj, path) {
        return path.split('.').reduce((current, key) => current?.[key], obj);
    }

    addLanguage(code, translations) {
        this.languages[code] = translations;
    }

    listLanguages() {
        return Object.keys(this.languages);
    }
}

module.exports = LanguageHandler;
