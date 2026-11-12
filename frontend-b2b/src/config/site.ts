// Public B2B showcase site configuration.
// Contact details are read from this single config file (NOT hardcoded into components),
// so they can be updated or overridden via env/build config without touching page components.

// NOTE: These are Owner-confirmed public business contact details.
// - WhatsApp: +86 186 6536 6380 (wa.me deep-link format strips "+" and spaces)
// - B2B email: partners@nuotaooutdoor.com (already referenced by existing B2B code/templates)
export const SITE_CONFIG = {
  company: {
    name: 'Nuotao Outdoor',
    tagline: 'Practical lightweight camping and hiking gear for retail and wholesale buyers.',
  },
  contact: {
    whatsappNumber: '+8618665366380', // international format, no "+", no spaces (wa.me requirement)
    whatsappDisplay: '+86 186 6536 6380',
    get whatsappUrl() {
      return `https://wa.me/${this.whatsappNumber}`
    },
    email: 'partners@nuotaooutdoor.com',
  },
} as const
