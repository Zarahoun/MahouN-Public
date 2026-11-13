/**
 * MSW request handlers for frontend tests.
 * Mocks the MAHOUN backend search endpoint so component tests run offline.
 */

import { http, HttpResponse } from 'msw';

export const searchVerdictsHandler = http.post(
  'http://localhost:8000/v1/search/verdicts',
  async ({ request }) => {
    const body = (await request.json()) as {
      query?: string;
      limit?: number;
      offset?: number;
      filters?: Record<string, unknown>;
    };

    const hits = [
      {
        verdict_id: 'verdict-001',
        case_type: 'اعتراض ثالث اجرایی',
        court_level: 'دادگاه تجدیدنظر استان',
        procedure_stage: 'تجدیدنظر',
        is_final: true,
        score: 0.92,
        section: 'appeal_reasoning',
        chunk_text:
          'متن أخذ از رأی دادگاه تجدیدنظر درباره اعتراض ثالث اجرایی نسبت به توقیف عملیات اجرای احکام.',
        case_number: '1402/123',
        date: '1402-05-15',
        judges: ['قاضی احمد', 'قاضی سارا'],
        parties: ['مدعی: علی احمدی', 'مدعا علیه: شرکت XYZ'],
        title: 'رأی اعتراض ثالث اجرایی پرونده شماره ۱۴۰۲/۱۲۳',
        law_articles: [
          { article: 'ماده 348', section: '۱', description: 'اعتراض ثالث اجرایی' },
          { article: 'ماده 349', section: null, description: 'شرایط قبولیت' },
        ],
        tags: ['اعتراض ثالث', 'اجرایی', 'توقیف'],
        full_text_url: 'https://example.com/verdicts/verdict-001',
        metadata: {},
      },
      {
        verdict_id: 'verdict-002',
        case_type: 'دعواى مدنی',
        court_level: 'دادگاه اول instance',
        procedure_stage: 'بدوي',
        is_final: false,
        score: 0.76,
        section: 'first_instance_summary',
        chunk_text: 'خلاصه رأی بدوی در مورد دعوای مدنی related to contract.',
        case_number: '1401/456',
        date: '1401-11-20',
        judges: [],
        parties: [],
        title: null,
        law_articles: [],
        tags: [],
        full_text_url: null,
        metadata: {},
      },
    ];

    return HttpResponse.json({
      results: hits,
      hits,
      total: hits.length,
      query: body.query || '',
      executionTime: 120,
      filters: body.filters,
    });
  }
);

export const handlers = [searchVerdictsHandler];
