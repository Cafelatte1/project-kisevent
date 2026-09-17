const fs = require('fs');
const path = require('path');
const axios = require('axios');
const cheerio = require('cheerio');

const BASE_URL = 'https://securities.koreainvestment.com/main/customer/notice/Event.jsp';
const HEADERS = { 'User-Agent': 'Mozilla/5.0' };
const CUSTGUBUNS = [
	{ code: '01', label: '영업점' },
	{ code: '02', label: '뱅키스' }
];
const IMAGE_DIR = path.join(__dirname, '..', 'public', 'data', 'images');

function listUrl(code) {
	return `${BASE_URL}?gubun=i&CUSTGUBUN=${code}`;
}

function detailUrl(num, code) {
	return `${BASE_URL}?gubun=i&cmd=TF04gb010002&num=${num}&currentPage=1&CUSTGUBUN=${code}`;
}

function absoluteUrl(src) {
	return new URL(src, BASE_URL).href;
}

function cleanText(value) {
	return value
		.split('\n')
		.map((line) => line.replace(/\s+/g, ' ').trim())
		.filter(Boolean)
		.join('\n');
}

async function fetchList(code) {
	const res = await axios.get(listUrl(code), { headers: HEADERS });
	const $ = cheerio.load(res.data);
	const events = [];

	$('.event_thum_box').each((i, el) => {
		const $el = $(el);
		const numMatch = /doView\('(\d+)'\)/.exec($el.attr('href') || '');
		if (!numMatch) return;

		const period = cleanText($el.find('.date .letter_0').text()).replace(/\n/g, ' ');
		const [periodStart, periodEnd] = period.split('~').map((s) => s.trim());
		const thumbnail = $el.find('.event_img img').attr('src');

		events.push({
			num: numMatch[1],
			title: cleanText($el.find('.title').text()),
			status: cleanText($el.find('.event_ing').text()) || null,
			periodStart: periodStart || null,
			periodEnd: periodEnd || null,
			summary: cleanText($el.find('.con').text()) || null,
			thumbnailUrl: thumbnail ? absoluteUrl(thumbnail) : null
		});
	});

	return events;
}

function mergeLists(lists) {
	const byNum = new Map();

	lists.forEach(({ label, events }) => {
		events.forEach((event) => {
			const existing = byNum.get(event.num);
			if (existing) {
				existing.targets.push(label);
			} else {
				byNum.set(event.num, { ...event, targets: [label], custgubun: event.custgubun });
			}
		});
	});

	return [...byNum.values()];
}

async function downloadImage(num, src) {
	const url = absoluteUrl(src);
	const ext = (path.extname(new URL(url).pathname).match(/^\.(png|jpe?g|gif|webp)$/i) || ['.png'])[0];
	const fileName = `${num}${ext.toLowerCase()}`;
	const res = await axios.get(url, { headers: HEADERS, responseType: 'arraybuffer' });
	fs.writeFileSync(path.join(IMAGE_DIR, fileName), res.data);
	return `/data/images/${fileName}`;
}

async function fetchDetail(num, code) {
	const res = await axios.get(detailUrl(num, code), { headers: HEADERS });
	const $ = cheerio.load(res.data);

	const $container = $('#ifrmContent');
	const $body = $container.find('.events_1').length ? $container.find('.events_1').first() : $container;

	$body.find('script, style, iframe, noscript, label').remove();
	$body.find('.blind, .offscreen, [style*="clip"]').remove();

	const text = cleanText($body.text()) || null;

	let imagePath = null;
	const imgSrc = $body.find('img').first().attr('src');
	if (imgSrc) {
		try {
			imagePath = await downloadImage(num, imgSrc);
		} catch (err) {
			console.error(`이벤트 ${num} 이미지 저장 실패:`, err.message);
		}
	}

	const departmentHtml = /<!--\s*담당자\s*-->([\s\S]*?)<!--b:e-->/.exec(res.data);
	const department = departmentHtml ? cleanText(cheerio.load(departmentHtml[1]).text()) || null : null;

	return { text, imagePath, department };
}

async function scrapeEvents() {
	fs.mkdirSync(IMAGE_DIR, { recursive: true });

	const lists = [];
	for (const { code, label } of CUSTGUBUNS) {
		const events = await fetchList(code);
		lists.push({ label, events: events.map((event) => ({ ...event, custgubun: code })) });
	}

	const merged = mergeLists(lists);
	const events = [];

	for (const event of merged) {
		const { custgubun, ...rest } = event;
		let detail = null;
		let department = null;

		try {
			const parsed = await fetchDetail(event.num, custgubun);
			detail = { text: parsed.text, imagePath: parsed.imagePath };
			department = parsed.department;
		} catch (err) {
			console.error(`이벤트 ${event.num} 상세 조회 실패:`, err.message);
		}

		events.push({ ...rest, department, detail });
	}

	return { fetchedAt: new Date().toISOString(), events };
}

module.exports = { scrapeEvents };
