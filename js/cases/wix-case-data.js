// Seeded Wix dataset for the StoryMap prototype.
//
// Every factual claim below is drawn from the public sources listed in `sources` (the same
// sources used in storymap_wix_real_value_demo.html). Everything else — the strategic
// reconstruction, diagnosis, narrative candidates, scores and recommendation — is StoryMap
// analysis and is labeled as such via `statementType`. Nothing here is invented data: no
// fabricated market share, sentiment, or momentum figures are introduced beyond what the
// sources state.
//
// This file is a seed for `analysis-service.js` (via case-utils.js's buildCaseDataset). A later
// version of this product would replace this file's role with live output from Agents 1-9,
// without changing the service interface or any UI component. See js/cases/hps-case-data.js for
// the second case — both share identical evidence-integrity rules via case-utils.js.

import { buildCaseDataset } from "../case-utils.js";

const RETRIEVED_AT = "2026-07-28";

const sources = [
  {
    id: "src_wix_q1_2026",
    companyId: "wix",
    title: "Wix Reports First Quarter 2026 Results",
    publisher: "Wix Press Room",
    sourceType: "press_release",
    url: "https://www.wix.com/press-room/home/post/wix-reports-first-quarter-2026-results",
    publishedAt: "2026-05-13",
    retrievedAt: RETRIEVED_AT,
    permissionStatus: "approved",
  },
  {
    id: "src_wix_harmony",
    companyId: "wix",
    title: "Wix Harmony: AI and you, building together",
    publisher: "Wix Blog",
    sourceType: "website",
    url: "https://www.wix.com/blog/omer-shai-wix-harmony-building-together-with-ai",
    publishedAt: "2026-01-21",
    retrievedAt: RETRIEVED_AT,
    permissionStatus: "approved",
  },
  {
    id: "src_wix_state_ai_report",
    companyId: "wix",
    title: "How Is AI Changing Website Creation? New Wix Report",
    publisher: "Wix Blog",
    sourceType: "website",
    url: "https://www.wix.com/blog/how-is-ai-changing-website-creation",
    publishedAt: "2026-07-02",
    retrievedAt: RETRIEVED_AT,
    permissionStatus: "approved",
  },
  {
    id: "src_webflow_home",
    companyId: "wix",
    title: "Webflow: The agentic web platform for modern businesses",
    publisher: "Webflow",
    sourceType: "competitor",
    url: "https://webflow.com/",
    publishedAt: "2026-07-01",
    retrievedAt: RETRIEVED_AT,
    permissionStatus: "approved",
  },
  {
    id: "src_webflow_ai_update",
    companyId: "wix",
    title: "Webflow's AI site builder, evolved",
    publisher: "Webflow Updates",
    sourceType: "competitor",
    url: "https://webflow.com/updates/ai-site-builder-evolved",
    publishedAt: "2026-02-05",
    retrievedAt: RETRIEVED_AT,
    permissionStatus: "approved",
  },
  {
    id: "src_squarespace_ai_visibility",
    companyId: "wix",
    title: "AI Visibility Helps Businesses Navigate the Shift to AI-Powered Search",
    publisher: "Squarespace Newsroom",
    sourceType: "competitor",
    url: "https://newsroom.squarespace.com/blog/ai-visibility-helps-businesses-navigate-the-shift-to-ai-powered-search",
    publishedAt: "2026-07-07",
    retrievedAt: RETRIEVED_AT,
    permissionStatus: "approved",
  },
];

// supportsIds is filled in programmatically below (see wireEvidenceSupportsIds) so it always
// matches the strategic choices, diagnosis findings and candidates that actually cite each item.
const evidence = [
  {
    id: "ev_self_description",
    sourceId: "src_wix_q1_2026",
    excerpt: "Wix describes itself as a website builder combining design tools and business solutions in one AI-powered platform.",
    paraphrase: "Wix's own current self-description is still anchored in the 'website builder' category.",
    evidenceType: "self-description",
    strength: "strong",
    freshness: "current",
    confidence: 0.9,
    scope: "company-wide",
    supportsIds: [],
  },
  {
    id: "ev_bookings_growth",
    sourceId: "src_wix_q1_2026",
    excerpt: "Q1 bookings were $585 million, up 15% year over year; revenue was $541 million, up 14%.",
    paraphrase: "Double-digit bookings and revenue growth in Q1 2026.",
    evidenceType: "business_growth",
    strength: "strong",
    freshness: "current",
    confidence: 0.9,
    scope: "company-wide",
    supportsIds: [],
  },
  {
    id: "ev_new_user_growth",
    sourceId: "src_wix_q1_2026",
    excerpt: "New-user cohort bookings increased about 46% year over year.",
    // Was "New-user bookings are accelerating faster than overall company growth" — that compares
    // this figure against ev_bookings_growth's separate 14-15% figures, which is a StoryMap
    // comparison, not something this excerpt states on its own. An atomic source_fact paraphrase
    // must restate only what its own excerpt says.
    paraphrase: "New-user cohort bookings grew about 46% year over year.",
    evidenceType: "market_adoption",
    strength: "strong",
    freshness: "current",
    confidence: 0.85,
    scope: "new users",
    supportsIds: [],
  },
  {
    id: "ev_harmony_model",
    sourceId: "src_wix_q1_2026",
    excerpt: "Wix Harmony runs on a proprietary AI model.",
    paraphrase: "Wix has invested in a proprietary AI model, not just a third-party wrapper.",
    evidenceType: "product_capability",
    strength: "moderate",
    freshness: "current",
    confidence: 0.7,
    scope: "Wix Harmony",
    supportsIds: [],
  },
  {
    id: "ev_base44_arr",
    sourceId: "src_wix_q1_2026",
    excerpt: "Base44 reached approximately $150 million in ARR as of May 2026.",
    paraphrase: "Base44, Wix's app-creation product, has meaningful independent revenue traction.",
    evidenceType: "business_growth",
    strength: "strong",
    freshness: "current",
    confidence: 0.85,
    scope: "Base44",
    supportsIds: [],
  },
  {
    id: "ev_harmony_framing",
    sourceId: "src_wix_harmony",
    excerpt: "Wix frames Harmony as combining AI speed with manual precision and creative control.",
    paraphrase: "Wix's own marketing already uses a speed-plus-control frame for Harmony specifically.",
    evidenceType: "positioning_statement",
    strength: "moderate",
    freshness: "current",
    confidence: 0.75,
    scope: "Wix Harmony",
    supportsIds: [],
  },
  {
    id: "ev_harmony_tension",
    sourceId: "src_wix_harmony",
    excerpt: "The stated customer tension is a trade-off between moving fast and retaining control.",
    paraphrase: "Wix explicitly names the speed-versus-control tension in its own product messaging.",
    evidenceType: "positioning_statement",
    strength: "moderate",
    freshness: "current",
    confidence: 0.7,
    scope: "Wix Harmony",
    supportsIds: [],
  },
  {
    id: "ev_aria_agent",
    sourceId: "src_wix_harmony",
    excerpt: "Harmony uses an AI agent, Aria, to create pages, layouts, components and content, while users can refine details manually.",
    paraphrase: "The product mechanism (Aria generates, users refine) is real and specific, not just marketing language.",
    evidenceType: "product_capability",
    strength: "moderate",
    freshness: "current",
    confidence: 0.75,
    scope: "Aria",
    supportsIds: [],
  },
  {
    id: "ev_harmony_positioning",
    sourceId: "src_wix_harmony",
    excerpt: "Wix presents the platform as professional-grade and scalable.",
    paraphrase: "Wix aspires to be seen as professional-grade and scalable, though this claim is largely self-asserted.",
    evidenceType: "aspiration",
    strength: "weak",
    freshness: "current",
    confidence: 0.4,
    scope: "Wix Harmony",
    supportsIds: [],
  },
  {
    id: "ev_publish_speed",
    sourceId: "src_wix_state_ai_report",
    excerpt: "Average time to publish a website fell from eight days to four.",
    paraphrase: "Wix reports a roughly 50% reduction in average time-to-publish.",
    evidenceType: "product_performance",
    strength: "strong",
    freshness: "current",
    confidence: 0.85,
    scope: "company-wide",
    supportsIds: [],
  },
  {
    id: "ev_user_editing",
    sourceId: "src_wix_state_ai_report",
    excerpt: "91% of users rewrite their own copy and nearly 70% replace images with their own.",
    paraphrase: "Most users actively edit AI-generated output rather than publishing it as-is.",
    evidenceType: "product_performance",
    strength: "strong",
    freshness: "current",
    confidence: 0.85,
    scope: "company-wide",
    supportsIds: [],
  },
  {
    id: "ev_aria_adoption",
    sourceId: "src_wix_state_ai_report",
    excerpt: "84% of non-AI premium sites use Aria at some point.",
    paraphrase: "Aria adoption is broad even among sites that don't end up fully AI-built.",
    evidenceType: "market_adoption",
    strength: "strong",
    freshness: "current",
    confidence: 0.8,
    scope: "company-wide",
    supportsIds: [],
  },
  {
    id: "ev_wix_interpretation",
    sourceId: "src_wix_state_ai_report",
    excerpt: "Wix interprets the evidence as AI increasing speed while users retain final control.",
    paraphrase: "The conclusion that users 'retain control' is Wix's own interpretation of its usage data, not an independently validated finding.",
    evidenceType: "vendor_interpretation",
    strength: "weak",
    freshness: "current",
    confidence: 0.35,
    scope: "company-wide",
    supportsIds: [],
  },
  {
    id: "ev_webflow_positioning",
    sourceId: "src_webflow_home",
    excerpt: "Webflow positions itself as an agentic web platform for modern businesses, emphasizing enterprise workflows, brand control, analytics and measurable pipeline.",
    paraphrase: "Webflow's current claim centers on 'agentic platform' plus enterprise workflow and measurable outcomes.",
    evidenceType: "competitor_positioning",
    strength: "moderate",
    freshness: "current",
    confidence: 0.75,
    scope: "Webflow",
    supportsIds: [],
  },
  {
    id: "ev_webflow_ai_output",
    sourceId: "src_webflow_ai_update",
    excerpt: "Webflow's AI site builder produces editable, multi-page sites with structure, styles and animations, refinable in production workflows and available to enterprise customers.",
    paraphrase: "Webflow's AI builder output is also positioned as editable and production-ready, not fully autonomous.",
    evidenceType: "competitor_positioning",
    strength: "moderate",
    freshness: "current",
    confidence: 0.7,
    scope: "Webflow",
    supportsIds: [],
  },
  {
    id: "ev_squarespace_ai_visibility",
    sourceId: "src_squarespace_ai_visibility",
    excerpt: "Squarespace positions AI Visibility as helping businesses understand and improve how they appear in AI-powered discovery, benchmarked against competitors.",
    paraphrase: "Squarespace's newest AI-era claim is about discoverability, a different problem than creation speed or control.",
    evidenceType: "competitor_positioning",
    strength: "moderate",
    freshness: "current",
    confidence: 0.7,
    scope: "Squarespace",
    supportsIds: [],
  },
];

// Every citation below is an EvidenceLink, not a bare id: it records not just *that* a source was
// cited but *how* it bears on this exact statement (relevance) and *why* (rationale). This
// exists because "the evidence is real" and "the evidence proves this specific claim" are
// different questions — e.g. Wix's Q1 revenue growth is real, strong evidence, but it says
// nothing about who Wix's chosen customers are, so it does not appear as evidence for
// sc_customers below. Confidence is not hand-authored: buildCaseDataset() (case-utils.js) derives
// it from the strength of the underlying EvidenceItem and the relevance of the link, and
// "context" or "conflicting" links are never allowed to raise it.
const strategicFoundation = [
  {
    id: "sc_customers",
    type: "customer",
    statement: "Individuals, entrepreneurs, agencies and businesses that need to create and operate a professional online presence.",
    statementType: "storymap_inference",
    evidence: [
      {
        evidenceId: "ev_self_description",
        relevance: "partial",
        rationale: "Names both design tools (implying individual/creative users) and business solutions (implying business customers), loosely suggesting a broad customer base — but it's a product description, not an explicit statement of target customer segments.",
      },
    ],
    confidence: 0,
    approvalStatus: "unreviewed",
  },
  {
    id: "sc_chosen_market",
    type: "market",
    statement: "Website creation and small-business digital operations, reached primarily online and self-serve, across the markets where Wix operates.",
    statementType: "storymap_inference",
    evidence: [
      {
        evidenceId: "ev_self_description",
        relevance: "partial",
        rationale: "The product description (design tools plus business solutions, AI-powered platform) implies this market category, but no source explicitly states Wix's market scope or geography — this is StoryMap reading it off the product, not a market statement Wix itself makes.",
      },
    ],
    confidence: 0,
    approvalStatus: "unreviewed",
  },
  {
    id: "sc_market_change",
    type: "market_change",
    statement: "AI is reducing the time and technical effort required to create websites and software, while users still want control over brand and quality.",
    statementType: "storymap_inference",
    evidence: [
      {
        evidenceId: "ev_publish_speed",
        relevance: "direct",
        rationale: "Directly evidences the 'AI reducing time and effort' half of the claim: average publishing time fell from eight days to four.",
      },
      {
        evidenceId: "ev_user_editing",
        relevance: "direct",
        rationale: "Directly evidences the 'users still want control over brand and quality' half of the claim: most users actively rewrite AI-generated copy and replace images rather than publishing as-is.",
      },
    ],
    confidence: 0,
    approvalStatus: "unreviewed",
  },
  {
    id: "sc_way_to_win",
    type: "way_to_win",
    statement: "Combine AI-assisted creation, manual control, business tools and scalable infrastructure in one platform.",
    statementType: "storymap_inference",
    evidence: [
      {
        evidenceId: "ev_harmony_framing",
        relevance: "direct",
        rationale: "Wix's own product framing explicitly combines AI speed with manual precision and creative control, matching the 'AI-assisted creation and manual control' half of the claim.",
      },
      {
        evidenceId: "ev_aria_agent",
        relevance: "direct",
        rationale: "Describes the actual mechanism — Aria generates, users refine — that instantiates the combine-AI-and-control strategy.",
      },
      {
        evidenceId: "ev_base44_arr",
        relevance: "partial",
        rationale: "Shows Base44 has real commercial traction, partially supporting the 'business tools' element of the claim — but ARR alone doesn't establish that Base44 is strategically combined with the rest of the platform.",
      },
    ],
    confidence: 0,
    approvalStatus: "unreviewed",
  },
  {
    id: "sc_capabilities",
    type: "capability",
    statement: "Wix Harmony, Aria, a proprietary AI model, a large existing user base, business applications, and Base44 are the company's stated capabilities.",
    statementType: "storymap_synthesis",
    evidence: [
      {
        evidenceId: "ev_harmony_model",
        relevance: "direct",
        rationale: "Directly confirms the proprietary-AI-model capability named in the statement.",
      },
      {
        evidenceId: "ev_aria_agent",
        relevance: "direct",
        rationale: "Directly confirms the Aria capability named in the statement.",
      },
      {
        evidenceId: "ev_base44_arr",
        relevance: "direct",
        rationale: "Confirms Base44 is a real, substantial capability rather than an announced but unproven product, by showing it has reached ~$150M in ARR.",
      },
    ],
    confidence: 0,
    approvalStatus: "unreviewed",
  },
  {
    id: "sc_proof",
    type: "proof",
    statement: "Public evidence shows faster site creation, strong Aria adoption, double-digit Q1 bookings and revenue growth, accelerated new-user bookings, and Base44 approaching $150M ARR.",
    statementType: "storymap_synthesis",
    evidence: [
      { evidenceId: "ev_publish_speed", relevance: "direct", rationale: "This exact statistic is one of the proof points the statement lists." },
      { evidenceId: "ev_aria_adoption", relevance: "direct", rationale: "This exact statistic is one of the proof points the statement lists." },
      { evidenceId: "ev_bookings_growth", relevance: "direct", rationale: "This exact statistic is one of the proof points the statement lists." },
      { evidenceId: "ev_new_user_growth", relevance: "direct", rationale: "This exact statistic is one of the proof points the statement lists." },
      { evidenceId: "ev_base44_arr", relevance: "direct", rationale: "This exact statistic is one of the proof points the statement lists." },
    ],
    confidence: 0,
    approvalStatus: "unreviewed",
  },
  {
    id: "sc_assumption_1",
    type: "assumption",
    statement: "Wix is assuming customers will value 'AI speed plus retained control' more than pure automation as AI tools mature.",
    statementType: "storymap_inference",
    evidence: [
      {
        evidenceId: "ev_harmony_tension",
        relevance: "direct",
        rationale: "Wix explicitly names the speed-versus-control trade-off as the customer tension it is designing for — exactly the assumption being described.",
      },
      {
        evidenceId: "ev_wix_interpretation",
        relevance: "direct",
        rationale: "Wix's own stated belief that customers value retained control is directly the assumption in question — though as a self-interpretation it is weak evidence, not independent validation.",
      },
    ],
    confidence: 0,
    approvalStatus: "unreviewed",
  },
  {
    id: "sc_risk_1",
    type: "risk",
    statement: "The product portfolio (Wix core, Harmony, Aria, Base44) risks reading as several separate innovations rather than one strategic direction.",
    statementType: "storymap_inference",
    evidence: [
      {
        evidenceId: "ev_harmony_model",
        relevance: "context",
        rationale: "Confirms Harmony exists as a distinctly named product — part of the pattern the risk describes, but not proof that the pattern causes confusion or fragmentation.",
      },
      {
        evidenceId: "ev_base44_arr",
        relevance: "context",
        rationale: "Confirms Base44 exists as a distinctly named, substantial product — part of the pattern the risk describes, but not proof that it causes fragmentation.",
      },
    ],
    confidence: 0,
    approvalStatus: "unreviewed",
  },
  {
    // Primary: changes who/what the narrative is even about — the most material scope question.
    id: "sc_unresolved_scope",
    type: "unresolved",
    statement: "Does the recommended narrative define Wix as a whole company, or only the Wix Harmony product line?",
    statementType: "leadership_decision",
    evidence: [],
    confidence: 0,
    approvalStatus: "unreviewed",
    priority: "primary",
  },
  {
    // Primary: "control" is the central word in the recommended one-sentence story — which kind
    // of control is meant materially changes what the narrative commits to in execution.
    id: "sc_unresolved_control",
    type: "unresolved",
    statement: "Does 'control' mean creative control, business control, data control, or a disciplined combination of all three?",
    statementType: "leadership_decision",
    evidence: [],
    confidence: 0,
    approvalStatus: "unreviewed",
    priority: "primary",
  },
  {
    id: "sc_unresolved_base44",
    type: "unresolved",
    statement: "How should Base44 fit into the corporate story — as proof of broader creation capability, or as a distinct product story?",
    statementType: "leadership_decision",
    evidence: [],
    confidence: 0,
    approvalStatus: "unreviewed",
    priority: "secondary",
  },
  {
    id: "sc_unresolved_outcomes",
    type: "unresolved",
    statement: "What business outcomes can Wix prove beyond faster website creation — revenue impact, retention, or operational savings for customers?",
    statementType: "leadership_decision",
    evidence: [],
    confidence: 0,
    approvalStatus: "unreviewed",
    priority: "secondary",
  },
  {
    id: "sc_unresolved_category",
    type: "unresolved",
    statement: "How far should Wix move beyond the website-builder category before it risks losing the category recognition it has already earned?",
    statementType: "leadership_decision",
    evidence: [],
    confidence: 0,
    approvalStatus: "unreviewed",
    priority: "secondary",
  },
];

const diagnosis = [
  {
    id: "df_category_narrow",
    title: "The current category label understates the business.",
    explanation: "“Website builder” is easy to understand, but it narrows Wix to site creation while the company is investing in AI agents, business tools, app creation and Base44.",
    significance: "high",
    statementType: "storymap_inference",
    evidence: [
      { evidenceId: "ev_self_description", relevance: "direct", rationale: "Is the exact narrow self-description ('website builder... AI-powered platform') the finding says understates the business." },
      { evidenceId: "ev_harmony_model", relevance: "partial", rationale: "Shows a proprietary AI capability exists beyond simple website building, partially supporting the 'understates the business' argument." },
      { evidenceId: "ev_base44_arr", relevance: "partial", rationale: "Shows a substantial, separate business (app creation) exists beyond website building, partially supporting the 'understates the business' argument." },
    ],
    confidence: 0,
    priority: "primary",
  },
  {
    id: "df_tension_underused",
    title: "The strongest customer tension is already visible but not consistently used as the corporate story.",
    explanation: "Wix has a clear, human problem to own: people want AI speed without losing control of quality, brand or detail. Today that idea lives inside Harmony's product messaging, not the corporate story.",
    significance: "high",
    statementType: "storymap_inference",
    evidence: [
      { evidenceId: "ev_harmony_framing", relevance: "direct", rationale: "Shows the speed-and-control tension is already used — but only in Harmony's own product messaging, directly supporting 'visible but not used as the corporate story.'" },
      { evidenceId: "ev_harmony_tension", relevance: "direct", rationale: "Confirms the tension is explicitly named, but only at the product level." },
      { evidenceId: "ev_publish_speed", relevance: "context", rationale: "Establishes that the 'speed' side of the tension is real, but says nothing about whether it's used as the corporate story." },
    ],
    confidence: 0,
    priority: "secondary",
  },
  {
    id: "df_strong_proof",
    title: "Wix has unusually strong proof for a speed-and-control narrative.",
    explanation: "The company can point to a roughly 50% reduction in average publishing time while users still actively rewrite copy and replace images — a rare case where usage data actually supports the intended story.",
    significance: "high",
    statementType: "storymap_synthesis", // combines the publish-speed and user-editing stats into one finding — no single excerpt says this sentence
    evidence: [
      { evidenceId: "ev_publish_speed", relevance: "direct", rationale: "Is the exact publishing-speed statistic the finding cites." },
      { evidenceId: "ev_user_editing", relevance: "direct", rationale: "Is the exact user-editing statistic the finding cites." },
      { evidenceId: "ev_aria_adoption", relevance: "direct", rationale: "Is the exact Aria-adoption statistic the finding cites as further proof strength." },
    ],
    confidence: 0,
    priority: "primary",
  },
  {
    id: "df_competitor_convergence",
    title: "Competitor language is converging around AI-enabled creation.",
    explanation: "Webflow emphasizes agentic creation, production-ready output and enterprise control. Wix therefore needs a sharper, more ownable idea than “AI website builder,” which is quickly becoming a category convention rather than a distinct claim.",
    significance: "medium",
    statementType: "storymap_inference",
    evidence: [
      { evidenceId: "ev_webflow_positioning", relevance: "direct", rationale: "Is the exact competitor claim ('agentic web platform') the finding describes as converging language." },
      { evidenceId: "ev_webflow_ai_output", relevance: "direct", rationale: "Is the exact competitor claim (editable, production-ready AI output) the finding describes." },
      { evidenceId: "ev_squarespace_ai_visibility", relevance: "direct", rationale: "Is a second competitor's AI-era claim, supporting that convergence is category-wide, not just one competitor." },
    ],
    confidence: 0,
    priority: "primary",
  },
  {
    id: "df_fragmentation_risk",
    title: "The portfolio risks feeling fragmented without one unifying story.",
    explanation: "Wix, Harmony, Aria and Base44 each have real value, but without one corporate story they can appear as separate innovations rather than parts of one strategic direction.",
    significance: "medium",
    statementType: "storymap_inference",
    evidence: [
      { evidenceId: "ev_harmony_model", relevance: "context", rationale: "Confirms Harmony exists as a separately branded product — part of the pattern the finding describes, not proof of fragmentation itself." },
      { evidenceId: "ev_base44_arr", relevance: "context", rationale: "Confirms Base44 exists as a separately branded, substantial product — part of the pattern, not proof of fragmentation itself." },
    ],
    confidence: 0,
    priority: "secondary",
  },
  {
    id: "df_unverified_interpretation",
    title: "Wix's claim that users “retain control” is the company's own interpretation, not independent validation.",
    explanation: "The underlying behavior (91% rewrite copy, ~70% replace images) is real usage data and strong evidence. But the conclusion that this proves customers feel in “control” is Wix's own framing of that data, not a finding from an independent source. StoryMap keeps these two claims separate rather than treating the interpretation as fact.",
    significance: "medium",
    statementType: "storymap_inference",
    evidence: [
      { evidenceId: "ev_wix_interpretation", relevance: "direct", rationale: "Is the exact vendor interpretation the finding is examining." },
      { evidenceId: "ev_user_editing", relevance: "direct", rationale: "Is the underlying behavioral data the interpretation is built on — directly relevant to judging whether the interpretation is justified." },
    ],
    confidence: 0,
    priority: "secondary",
  },
];

const candidates = [
  {
    id: "cand_creation_without_compromise",
    name: "Creation without compromise",
    oneSentenceStory: "Wix gives people the speed of AI without forcing them to give up the control, quality and individuality that make their business their own.",
    sevenParts: {
      context: "AI is making it possible to create websites, software and business experiences far faster than before.",
      tension: "Speed can come with a loss of control, distinctiveness or confidence in the finished result.",
      belief: "AI should expand what people can create without taking ownership of the result away from them.",
      role: "Wix combines AI assistance, precise manual control, business tools and scalable infrastructure in one creation environment.",
      value: "People can move from idea to a professional, working digital business faster while keeping the result recognizably theirs.",
      proof: "Public Wix evidence indicates faster publishing, strong use of AI assistance and continued active user editing.",
      direction: "Expand from website creation toward a broader platform where people and AI build and operate digital businesses together.",
    },
    strategicLogic: [
      "Starts with a real customer tension rather than a product category.",
      "Connects Harmony, Aria, business tools and future AI products under one idea.",
      "Uses Wix's strongest and most specific evidence: faster creation with continued human editing and control.",
      "Differentiates from tools that emphasize automation alone.",
    ],
    customerRelevance: "Speaks directly to a tension customers already feel: AI makes creation faster, but they still want the result to look and feel like their own business, not a generic template.",
    differentiation: "More specific than “AI-powered website builder” and more human than “AI operating system.” Competitors emphasize automation or enterprise workflow, not this speed-versus-control tension.",
    tradeoffs: [
      "Chooses a human tension over a broad product-category claim, so it says less about the full breadth of the product portfolio.",
      "De-emphasizes enterprise and operations messaging in favor of a creation-and-control story.",
    ],
    risks: [
      "The story must expand beyond design control to show that Wix also helps customers operate and grow their businesses.",
      "If “control” is not clearly defined in execution, the claim risks sounding like marketing language rather than a distinct position.",
    ],
    claims: [
      { evidenceId: "ev_publish_speed", relevance: "direct", rationale: "Directly evidences the 'speed' half of this candidate's core claim." },
      { evidenceId: "ev_user_editing", relevance: "direct", rationale: "Directly evidences the 'without giving up control' half of this candidate's core claim." },
      { evidenceId: "ev_aria_adoption", relevance: "direct", rationale: "Directly evidences that AI assistance is broadly used, supporting the 'speed of AI' half of the claim." },
      { evidenceId: "ev_harmony_tension", relevance: "direct", rationale: "Is Wix's own statement of the exact speed-versus-control tension this candidate's story is built on." },
    ],
    scores: { "Strategic fit": 5, "Customer relevance": 5, "Differentiation": 4, "Evidence strength": 5, "Durability": 4 },
    criticFindings: [
      "Passes strategic-accuracy check: matches Harmony's stated design intent.",
      "Passes evidence check: all four cited sources directly and specifically support this claim, not just company context in general.",
      "Flagged: “control” is currently undefined at the corporate level — it could slide into generic language if not made concrete in execution.",
    ],
    status: "recommended",
  },
  {
    id: "cand_ai_operating_system",
    name: "The AI operating system for online business",
    oneSentenceStory: "Wix brings creation, operations and growth together in one AI-powered system for building and running a business online.",
    sevenParts: {
      context: "Businesses increasingly run every function — site, commerce, marketing, operations — through software rather than manual processes.",
      tension: "Business owners must stitch together many disconnected tools to launch and run an online business.",
      belief: "Creation and operation should live in one connected AI-powered system, not a collection of point tools.",
      role: "Wix positions itself as the operating layer beneath a business's entire online presence — creation, commerce, marketing and app development.",
      value: "Businesses get one system instead of many, reducing integration work and giving AI a full view of the business to act on.",
      proof: "Base44 approaching $150M ARR and double-digit bookings and revenue growth show platform-wide traction beyond website creation alone.",
      direction: "Extend from website creation into a full AI-run operating layer for online businesses.",
    },
    strategicLogic: [
      "Better reflects Wix's broad product portfolio (sites, commerce, marketing, Base44).",
      "Creates room for future products without needing to rename the story again.",
      "Positions Wix above the website-builder category entirely.",
    ],
    customerRelevance: "Appeals to businesses juggling multiple disconnected tools, but is less concrete for individuals and small creators who only need a website.",
    differentiation: "Broader than most competitor claims, but “operating system” is a well-worn category label used across software generally — not distinct to Wix.",
    tradeoffs: [
      "Chooses breadth and platform ambition over the more specific creation-and-control tension.",
      "De-emphasizes the concrete, provable publishing-speed story in favor of a more abstract systems claim.",
    ],
    risks: [
      "“Operating system” is abstract and difficult to own; several company types across software already make this claim.",
      "May overstate maturity for customer segments who use Wix only for a website today.",
    ],
    claims: [
      { evidenceId: "ev_base44_arr", relevance: "direct", rationale: "Directly evidences that Wix has a real, substantial product beyond website creation, supporting the 'operating system beyond website creation' claim." },
      { evidenceId: "ev_bookings_growth", relevance: "context", rationale: "Shows overall company growth, but doesn't specifically support an 'operating system' positioning over any other growth narrative." },
      { evidenceId: "ev_new_user_growth", relevance: "context", rationale: "Shows new-user momentum, but doesn't specifically support an 'operating system' positioning over any other growth narrative." },
    ],
    scores: { "Strategic fit": 5, "Customer relevance": 4, "Differentiation": 3, "Evidence strength": 3, "Durability": 5 },
    criticFindings: [
      "Flagged: “operating system” is a category convention already used broadly across software — real differentiation risk.",
      "Flagged: only one of three cited proof points (Base44's ARR) directly supports this specific claim — the other two are general company growth, not evidence of an operating-system positioning specifically.",
      "Passes strategic-fidelity check against Wix's stated multi-product direction.",
    ],
    status: "candidate",
  },
  {
    id: "cand_idea_to_business",
    name: "From idea to working business",
    oneSentenceStory: "Wix helps anyone turn an idea into a professional, working online business faster than before.",
    sevenParts: {
      context: "More people are trying to start an online business without technical or design skills.",
      tension: "Turning an idea into something real and professional-looking still takes more time, skill or money than most people have.",
      belief: "Anyone with an idea should be able to build a working, professional online business, not just a website.",
      role: "Wix is the fastest path from an idea to a working, professional online business.",
      value: "People move from concept to a live, credible business presence faster, without needing design or technical expertise.",
      proof: "Publishing time fell from eight days to four, and new-user bookings grew about 46% year over year.",
      direction: "Keep lowering the time and skill needed to go from idea to a working online business.",
    },
    strategicLogic: [
      "Simple and accessible to a broad, non-technical audience.",
      "Connects creation speed directly to a business outcome.",
      "Fits Wix's long-standing commitment to making creation accessible.",
    ],
    customerRelevance: "Broadly relevant to first-time business owners and solo creators; less specific for agencies or already-established businesses.",
    differentiation: "The weakest of the three options: “idea to working business, faster” is a claim several competitors can make in similar terms.",
    tradeoffs: [
      "Chooses broad accessibility over a sharper, more ownable position.",
      "Says little about what makes Wix specifically different from other creation tools.",
    ],
    risks: [
      "Differentiation is weak enough to risk sounding interchangeable with competitors.",
      "Does not showcase Wix's more advanced AI or business-platform capabilities.",
    ],
    claims: [
      { evidenceId: "ev_publish_speed", relevance: "direct", rationale: "Directly evidences the 'faster than before' half of this candidate's claim." },
      { evidenceId: "ev_new_user_growth", relevance: "context", rationale: "Shows new-user momentum, which is consistent with — but doesn't specifically prove — an 'idea to working business' framing over any other framing." },
    ],
    scores: { "Strategic fit": 4, "Customer relevance": 5, "Differentiation": 2, "Evidence strength": 3, "Durability": 4 },
    criticFindings: [
      "Flagged: differentiation score (2/5) is close to the Decision Agent's non-differentiation gate — several competitors can credibly make a similar claim.",
      "Flagged: only the publishing-speed statistic directly supports this specific framing — new-user growth is general momentum, not proof of an 'idea to business' claim over any other.",
      "Passes customer-relevance check: broad appeal to first-time business owners.",
    ],
    status: "candidate",
  },
];

const audiences = [
  { id: "aud_smb_creators", name: "Individual creators & small business owners", description: "People choosing a platform to build and run an online presence for the first time." },
  { id: "aud_agencies", name: "Agencies & consultants", description: "Professionals building sites and digital products for multiple clients." },
  { id: "aud_growing_businesses", name: "Growing businesses", description: "Established small and mid-size businesses adding commerce, marketing or app functionality." },
];

const competitorContrasts = [
  {
    id: "cc_webflow",
    competitor: "Webflow",
    contrast: "Webflow leads with an “agentic web platform” claim centered on enterprise workflow, brand control and measurable pipeline. It does not foreground the speed-versus-control tension for everyday creators that Wix's usage data supports.",
    evidence: [
      { evidenceId: "ev_webflow_positioning", relevance: "direct", rationale: "Is the exact Webflow claim being contrasted against Wix's positioning." },
      { evidenceId: "ev_webflow_ai_output", relevance: "direct", rationale: "Is the exact Webflow AI-output claim being contrasted against Wix's positioning." },
    ],
  },
  {
    id: "cc_squarespace",
    competitor: "Squarespace",
    contrast: "Squarespace's newest positioning centers on AI visibility in AI-powered search — a different problem (being found) than the one Wix's narrative addresses (creating fast without losing control).",
    evidence: [
      { evidenceId: "ev_squarespace_ai_visibility", relevance: "direct", rationale: "Is the exact Squarespace claim being contrasted against Wix's positioning." },
    ],
  },
];

const recommendation = {
  candidateId: "cand_creation_without_compromise",
  recommendedDecision: "Position Wix around AI speed with retained human control, while preserving website creation as the proof point — not the limits — of the company.",
  whyItWins: "It starts from a real customer tension instead of a product category, uses Wix's strongest and most specific evidence — faster publishing plus continued human editing — and can grow to cover websites, business tools and app creation without needing to be redefined again.",
  whyCustomersCare: "AI makes creation faster, but businesses still need the result to feel credible, distinctive and under their control. Wix has product design and usage evidence showing AI and manual refinement are used together, not as substitutes.",
  whyCredible: "Wix has public evidence — publishing time cut roughly in half, and high rates of continued manual editing — that directly supports the speed-and-control claim, rather than requiring customers to take the claim on faith.",
  howDifferent: "Webflow leads with an agentic-platform and enterprise-workflow claim; Squarespace leads with AI-discovery visibility. Neither centers the speed-versus-control tension that Wix already has product and usage evidence for.",
  missingEvidence: [
    "Independent (non-Wix) validation that customers actually perceive greater control — not just that they edit AI output.",
    "Evidence connecting the narrative to Base44 and to business outcomes beyond website creation.",
    "Customer research on what “control” means to different segments — creative, operational or data control.",
  ],
  whyOthersNotSelected: {
    cand_ai_operating_system: "Strategically well-supported but “operating system” is a crowded category convention that is hard to own, and may overstate maturity for customers who use Wix mainly for a website today.",
    cand_idea_to_business: "Broadly appealing and accessible, but differentiation is weak — several competitors can make a similar claim in similar terms.",
  },
};

const narrativeMap = {
  id: "nm_wix_v1",
  companyId: "wix",
  version: 1,
  status: "draft",
  candidateId: "cand_creation_without_compromise",
  coreNarrative: "Wix gives people the speed of AI without forcing them to give up the control, quality and individuality that make their business their own.",
  sevenParts: {
    context: "AI is making it possible to create websites, software and business experiences far faster than before.",
    tension: "Speed can come with a loss of control, distinctiveness or confidence in the finished result.",
    belief: "AI should expand what people can create without taking ownership of the result away from them.",
    role: "Wix combines AI assistance, precise manual control, business tools and scalable infrastructure in one creation environment.",
    value: "People can move from idea to a professional, working digital business faster while keeping the result recognizably theirs.",
    proof: "Public Wix evidence indicates faster publishing, strong use of AI assistance and continued active user editing.",
    direction: "Expand from website creation toward a broader platform where people and AI build and operate digital businesses together.",
  },
  // Explicit, named claims — not a flat evidence list. Each one is traceable to specific
  // sources, so the map never shows a repeated, unlabeled "Wix Blog" chip standing in for
  // several different things the map is actually asserting.
  coreClaims: [
    {
      id: "claim_publish_speed",
      statement: "AI reduces website publishing time.",
      evidence: [
        { evidenceId: "ev_publish_speed", relevance: "direct", rationale: "Directly evidences this claim: average publishing time fell from eight days to four." },
      ],
    },
    {
      id: "claim_user_refine",
      statement: "Users continue to refine AI-generated outputs.",
      evidence: [
        { evidenceId: "ev_user_editing", relevance: "direct", rationale: "Directly evidences this claim: most users actively rewrite AI-generated copy and replace images rather than publishing as-is." },
      ],
    },
    {
      id: "claim_combine_ai_manual",
      statement: "Wix combines AI creation with manual editing.",
      evidence: [
        { evidenceId: "ev_aria_agent", relevance: "direct", rationale: "Describes the exact mechanism — Aria generates, users refine — that this claim asserts." },
        { evidenceId: "ev_harmony_tension", relevance: "direct", rationale: "Wix's own stated design intent names exactly this combination." },
      ],
    },
    {
      id: "claim_expansion",
      statement: "Wix is expanding beyond traditional website creation.",
      evidence: [
        { evidenceId: "ev_base44_arr", relevance: "direct", rationale: "Base44 (~$150M ARR) is itself an instance of expansion into app creation beyond website building." },
        { evidenceId: "ev_harmony_model", relevance: "partial", rationale: "A proprietary AI model investment is consistent with expansion beyond a simple website builder, but doesn't by itself prove the expansion claim." },
      ],
    },
  ],
  audienceIds: audiences.map((a) => a.id),
  competitorContrastIds: competitorContrasts.map((c) => c.id),
  unresolvedQuestions: strategicFoundationUnresolvedStatements(),
  createdAt: "2026-07-28",
  likelyObjections: [
    "“Control” is vague until we define what kind of control we mean.",
    "This doesn't yet explain how Base44 fits into the story.",
    "The narrative needs proof beyond website creation to justify a bigger claim later.",
  ],
  weakOrUnsupportedClaims: [
    "Wix's claim that customers “retain control” is the company's own interpretation of usage data, not independently validated.",
    "No independent (non-Wix) evidence yet connects this narrative to Base44 or to business outcomes beyond website creation.",
  ],
};

function strategicFoundationUnresolvedStatements() {
  return strategicFoundation.filter((c) => c.type === "unresolved").map((c) => c.statement);
}

const caseContext = {
  id: "wix",
  selectorLabel: "Wix public demonstration",
  selectorDescription: "A website-builder company publicly expanding into AI-assisted creation and business tools.",
  productTagline: "StoryMap helps companies decide what they should be known for — then keeps that story current by testing it against strategy, evidence and competitive context.",
  company: {
    id: "wix",
    name: "Wix",
    oneLiner: "Wix helps people and businesses build websites and run parts of their business online.",
  },
  whyThisCompany: "Wix is a useful demonstration case because the company is evolving beyond its original identity as a website builder. It is expanding into AI-assisted creation, business tools and application development. That creates a real narrative challenge.",
  headline: "How should Wix explain what it is becoming without losing the recognition it already has?",
  narrativeQuestion: "Should Wix continue to define itself primarily as a website builder, or adopt a broader story that better reflects where the company is going?",
  whatStoryMapWillDo: [
    "Reconstruct what the company is trying to achieve from public strategy, product and performance information.",
    "Identify where the current story is too narrow, unclear or similar to competitors.",
    "Develop several distinct ways the company could explain its future.",
    "Test each option against customer relevance, differentiation and evidence.",
    "Recommend the strongest story and show the trade-offs.",
    "Turn the selected direction into a structured Narrative Map.",
  ],
  disclosure: "This is an independent demonstration built from publicly available information. Wix did not provide internal documents and has not approved the analysis.",
  disclosureExtended: "In a real customer engagement, StoryMap would also use internal strategy documents, leadership interviews, customer research, business results and the company's existing narrative. That would allow the product to make a more complete and precise recommendation.",
};

export const WIX_DATASET = buildCaseDataset({
  caseContext,
  sources,
  evidence,
  strategicFoundation,
  diagnosis,
  candidates,
  audiences,
  competitorContrasts,
  recommendation,
  narrativeMap,
});
