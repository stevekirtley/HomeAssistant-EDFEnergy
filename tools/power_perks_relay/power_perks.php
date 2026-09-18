<?php
/**
 * EDF Power Perks relay.
 *
 * EDF announce Power Perks free electricity sessions by SMS only - nothing in their
 * API or app carries them ahead of time. This endpoint receives the text (from an iOS
 * Shortcut on the phone that holds the registered mobile number), parses out the date
 * and time window, and publishes the resulting sessions as JSON for the Home Assistant
 * integration to poll. Hosting it here rather than posting straight to Home Assistant
 * means a text is never lost while Home Assistant is down, and anyone else using the
 * integration gets the same sessions.
 *
 * Actions (?action=):
 *   ingest    POST {text, received_at?, sender?}   token required   store + parse one text
 *   sessions  GET                                   public           parsed sessions (last 60 days onward)
 *   parse     GET  ?text=...                        public           dry-run the parser, nothing stored
 *   messages  GET                                   token required   raw stored texts, for debugging
 *   health    GET                                   public
 *
 * The token is passed as an X-Token header or a ?token= query parameter. It lives in
 * config.php next to this file:  <?php return ['ingest_token' => 'long-random-string'];
 * Ingest is disabled until a token is configured.
 *
 * The sessions feed is served to the HomeAssistant-EDFEnergy integration, identified by
 * its User-Agent, and to anyone holding the token. That is a deterrent rather than a lock -
 * the integration is open source, so the user agent is no secret - but it keeps the feed
 * out of casual scrapers and other projects, and a per-address rate limit keeps the cost
 * of anyone who does copy it negligible.
 *
 * Storage is two JSON files in cache/ (must be writable by the web server):
 *   power_perks_messages.json   every text received, with its parse result
 *   power_perks_overrides.json  optional, hand-edited: [{code, start, end}] to add a
 *                               session the parser missed, or [{code, remove: true}]
 *                               to drop one it got wrong. Overrides win on a code clash.
 *
 * PHP 7.4+. No dependencies.
 */

declare(strict_types=1);

const RETENTION_DAYS = 60;
const TIMEZONE = 'Europe/London';

// ---------------------------------------------------------------------------
// Parser
// ---------------------------------------------------------------------------

const MONTHS = [
    'jan' => 1, 'feb' => 2, 'mar' => 3, 'apr' => 4, 'may' => 5, 'jun' => 6,
    'jul' => 7, 'aug' => 8, 'sep' => 9, 'oct' => 10, 'nov' => 11, 'dec' => 12,
];
const WEEKDAYS = ['mon' => 1, 'tue' => 2, 'wed' => 3, 'thu' => 4, 'fri' => 5, 'sat' => 6, 'sun' => 7];

/**
 * Parse an EDF Power Perks text into a session.
 *
 * Returns ['start' => DateTimeImmutable, 'end' => DateTimeImmutable, 'code' => string]
 * or ['error' => string] describing what could not be found. EDF have a habit of
 * rewording their messages, so this keys on three things only: the words "Power Perks",
 * a date (explicit, or today/tomorrow/a weekday resolved against when the text arrived)
 * and a time window in any common form.
 */
function parse_power_perks_message(string $text, DateTimeImmutable $received): array
{
    $tz = new DateTimeZone(TIMEZONE);
    $received = $received->setTimezone($tz);
    $normalised = preg_replace('/\s+/u', ' ', $text) ?? $text;

    if (!preg_match('/power\s*-?\s*perks?/i', $normalised)) {
        return ['error' => 'no "Power Perks" mention'];
    }

    $date = extract_date($normalised, $received);
    if ($date === null) {
        return ['error' => 'no date found'];
    }

    $window = extract_time_window($normalised);
    if ($window === null) {
        return ['error' => 'no time window found'];
    }

    $start = $date->setTime($window['start'][0], $window['start'][1]);
    $end = $date->setTime($window['end'][0], $window['end'][1]);
    if ($end <= $start) {
        // A window that runs past midnight (e.g. 10pm-2am).
        $end = $end->modify('+1 day');
    }

    return [
        'start' => $start,
        'end' => $end,
        'code' => 'power_perks_' . $start->format('YmdHi'),
    ];
}

/** The calendar date the text refers to, at midnight local time, or null. */
function extract_date(string $text, DateTimeImmutable $received): ?DateTimeImmutable
{
    $today = $received->setTime(0, 0);
    $months = implode('|', array_keys(MONTHS));

    // "19 September", "19th Sept 2026", "September 19", "Sept 19th, 2026"
    if (preg_match("/\\b(\\d{1,2})(?:st|nd|rd|th)?\\s+($months)[a-z]*\\.?(?:,?\\s+(\\d{4}))?\\b/i", $text, $m)) {
        return resolve_explicit_date((int)$m[1], MONTHS[strtolower(substr($m[2], 0, 3))], $m[3] ?? '', $today);
    }
    if (preg_match("/\\b($months)[a-z]*\\.?\\s+(\\d{1,2})(?:st|nd|rd|th)?\\b(?:,?\\s+(\\d{4}))?/i", $text, $m)) {
        return resolve_explicit_date((int)$m[2], MONTHS[strtolower(substr($m[1], 0, 3))], $m[3] ?? '', $today);
    }
    // "19/09", "19/09/2026", "19-09-26"
    if (preg_match('/\b(\d{1,2})[\/\-](\d{1,2})(?:[\/\-](\d{2,4}))?\b/', $text, $m)) {
        $year = $m[3] ?? '';
        if (strlen($year) === 2) {
            $year = '20' . $year;
        }
        return resolve_explicit_date((int)$m[1], (int)$m[2], $year, $today);
    }

    if (preg_match('/\btomorrow\b/i', $text)) {
        return $today->modify('+1 day');
    }
    if (preg_match('/\b(today|tonight|this (?:morning|afternoon|evening))\b/i', $text)) {
        return $today;
    }

    // "on Saturday", "this Saturday": the next such day, counting today.
    $weekdays = implode('|', array_keys(WEEKDAYS));
    if (preg_match("/\\b($weekdays)[a-z]*\\b/i", $text, $m)) {
        $target = WEEKDAYS[strtolower(substr($m[1], 0, 3))];
        $ahead = ($target - (int)$today->format('N') + 7) % 7;
        return $today->modify("+{$ahead} days");
    }

    return null;
}

function resolve_explicit_date(int $day, int $month, string $year, DateTimeImmutable $today): ?DateTimeImmutable
{
    if ($month < 1 || $month > 12 || $day < 1 || $day > 31) {
        return null;
    }
    $yearNumber = $year !== '' ? (int)$year : (int)$today->format('Y');
    $candidate = $today->setDate($yearNumber, $month, $day);
    if (!checkdate($month, $day, $yearNumber)) {
        return null;
    }
    // No year given and the date is well in the past: it must mean next year (a text sent
    // on 30 December about 2 January).
    if ($year === '' && $candidate < $today->modify('-30 days')) {
        $candidate = $candidate->modify('+1 year');
    }
    return $candidate;
}

/**
 * The first "X to Y" pair of clock times in the text, as [[h, m], [h, m]] in 24h, or null.
 *
 * Accepts 4am-4pm, 4am to 4pm, between 4am and 4pm, 04:00-16:00, 4.30pm, 4 p.m., midday,
 * noon and midnight. A missing am/pm on one side is inferred from the other: "4-4pm" is
 * 04:00-16:00 because 16:00-16:00 is not a window.
 */
function extract_time_window(string $text): ?array
{
    $time = '(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?|(midday|noon|midnight)';
    $separator = '\s*(?:-|–|—|to|until|till|and|through)\s*';
    $pattern = "/(?:between\\s+)?(?:$time)$separator(?:$time)/iu";

    if (!preg_match_all($pattern, $text, $matches, PREG_SET_ORDER)) {
        return null;
    }

    foreach ($matches as $m) {
        $first = clock_parts($m[1] ?? '', $m[2] ?? '', $m[3] ?? '', $m[4] ?? '');
        $second = clock_parts($m[5] ?? '', $m[6] ?? '', $m[7] ?? '', $m[8] ?? '');
        if ($first === null || $second === null) {
            continue;
        }
        // Bare numbers on both sides with no am/pm and no minutes are more likely a date
        // ("19-09") than a window; the date regexes already own that shape.
        if ($first['meridiem'] === '' && $second['meridiem'] === '' && !$first['explicit'] && !$second['explicit']) {
            continue;
        }
        $resolved = resolve_meridiems($first, $second);
        if ($resolved !== null) {
            return $resolved;
        }
    }
    return null;
}

/** @return array{hour:int, minute:int, meridiem:string, explicit:bool}|null */
function clock_parts(string $hour, string $minute, string $meridiem, string $word): ?array
{
    $word = strtolower($word);
    if ($word !== '') {
        $hour24 = $word === 'midnight' ? 0 : 12;
        return ['hour' => $hour24, 'minute' => 0, 'meridiem' => 'x', 'explicit' => true];
    }
    if ($hour === '') {
        return null;
    }
    $h = (int)$hour;
    $m = $minute === '' ? 0 : (int)$minute;
    if ($h > 24 || $m > 59) {
        return null;
    }
    $mer = strtolower(str_replace('.', '', $meridiem));
    if ($mer !== '' && $h > 12) {
        return null;
    }
    return ['hour' => $h, 'minute' => $m, 'meridiem' => $mer, 'explicit' => $minute !== '' || $mer !== ''];
}

function to_24h(int $hour, string $meridiem): int
{
    if ($meridiem === 'am') {
        return $hour === 12 ? 0 : $hour;
    }
    if ($meridiem === 'pm') {
        return $hour === 12 ? 12 : $hour + 12;
    }
    return $hour === 24 ? 0 : $hour;
}

/** @return array{start: int[], end: int[]}|null */
function resolve_meridiems(array $first, array $second): ?array
{
    $firstMer = $first['meridiem'];
    $secondMer = $second['meridiem'];
    $inferred = ['am', 'pm'];

    $candidates = [];
    if ($firstMer === '' && in_array($secondMer, $inferred, true)) {
        $other = $secondMer === 'am' ? 'pm' : 'am';
        $candidates = [[$secondMer, $secondMer], [$other, $secondMer]];
    } elseif ($secondMer === '' && in_array($firstMer, $inferred, true)) {
        $other = $firstMer === 'am' ? 'pm' : 'am';
        $candidates = [[$firstMer, $firstMer], [$firstMer, $other]];
    } else {
        $candidates = [[$firstMer, $secondMer]];
    }

    foreach ($candidates as [$fm, $sm]) {
        $startHour = to_24h($first['hour'], $fm === 'x' ? '' : $fm);
        $endHour = to_24h($second['hour'], $sm === 'x' ? '' : $sm);
        if ($startHour > 23 || $endHour > 23) {
            continue;
        }
        $startMinutes = $startHour * 60 + $first['minute'];
        $endMinutes = $endHour * 60 + $second['minute'];
        if ($startMinutes === $endMinutes) {
            continue;
        }
        if (count($candidates) > 1 && $endMinutes < $startMinutes) {
            // An inferred meridiem that makes the window run backwards is the wrong guess.
            continue;
        }
        return [
            'start' => [$startHour, $first['minute']],
            'end' => [$endHour, $second['minute']],
        ];
    }
    return null;
}

// ---------------------------------------------------------------------------
// Storage
// ---------------------------------------------------------------------------

function cache_dir(): string
{
    return __DIR__ . '/cache';
}

function read_json_file(string $path): array
{
    if (!is_file($path)) {
        return [];
    }
    $data = json_decode((string)file_get_contents($path), true);
    return is_array($data) ? $data : [];
}

function write_json_file(string $path, array $data): void
{
    $dir = dirname($path);
    if (!is_dir($dir) && !mkdir($dir, 0775, true) && !is_dir($dir)) {
        throw new RuntimeException("Cannot create $dir");
    }
    $tmp = $path . '.tmp';
    file_put_contents($tmp, json_encode($data, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE), LOCK_EX);
    rename($tmp, $path);
}

function messages_path(): string
{
    return cache_dir() . '/power_perks_messages.json';
}

function overrides_path(): string
{
    return cache_dir() . '/power_perks_overrides.json';
}

function message_id(string $text, DateTimeImmutable $received): string
{
    $normalised = strtolower(trim(preg_replace('/\s+/u', ' ', $text) ?? $text));
    return substr(sha1($normalised . '|' . $received->format('Y-m-d')), 0, 16);
}

/** Store one text, parse it, and return the stored record. Re-sending the same text is a no-op. */
function ingest_message(string $text, DateTimeImmutable $received, string $sender): array
{
    $messages = read_json_file(messages_path());
    $id = message_id($text, $received);
    foreach ($messages as $existing) {
        if (($existing['id'] ?? '') === $id) {
            $existing['duplicate'] = true;
            return $existing;
        }
    }

    $parsed = parse_power_perks_message($text, $received);
    $record = [
        'id' => $id,
        'received_at' => $received->format(DATE_ATOM),
        'sender' => $sender,
        'text' => $text,
        'session' => isset($parsed['error']) ? null : [
            'code' => $parsed['code'],
            'start' => $parsed['start']->format(DATE_ATOM),
            'end' => $parsed['end']->format(DATE_ATOM),
        ],
        'parse_error' => $parsed['error'] ?? null,
    ];
    $messages[] = $record;

    // Keep the raw log bounded.
    $cutoff = $received->modify('-' . (RETENTION_DAYS * 2) . ' days');
    $messages = array_values(array_filter($messages, function (array $m) use ($cutoff): bool {
        $at = DateTimeImmutable::createFromFormat(DATE_ATOM, (string)($m['received_at'] ?? ''));
        return $at === false || $at >= $cutoff;
    }));

    write_json_file(messages_path(), $messages);
    return $record;
}

/** The published sessions: parsed texts plus overrides, deduplicated by code, recent first purged. */
function build_sessions(DateTimeImmutable $now): array
{
    $byCode = [];
    foreach (read_json_file(messages_path()) as $message) {
        $session = $message['session'] ?? null;
        if (!is_array($session) || empty($session['code'])) {
            continue;
        }
        $byCode[$session['code']] = [
            'code' => $session['code'],
            'start' => $session['start'],
            'end' => $session['end'],
            'source' => 'power_perks',
            'received_at' => $message['received_at'] ?? null,
            'text' => $message['text'] ?? null,
        ];
    }
    foreach (read_json_file(overrides_path()) as $override) {
        $code = (string)($override['code'] ?? '');
        if ($code === '') {
            continue;
        }
        if (!empty($override['remove'])) {
            unset($byCode[$code]);
            continue;
        }
        if (empty($override['start']) || empty($override['end'])) {
            continue;
        }
        $byCode[$code] = [
            'code' => $code,
            'start' => $override['start'],
            'end' => $override['end'],
            'source' => 'power_perks',
            'received_at' => $override['received_at'] ?? null,
            'text' => $override['text'] ?? 'manual override',
        ];
    }

    $cutoff = $now->modify('-' . RETENTION_DAYS . ' days');
    $sessions = array_values(array_filter($byCode, function (array $s) use ($cutoff): bool {
        $end = DateTimeImmutable::createFromFormat(DATE_ATOM, (string)$s['end']);
        return $end !== false && $end >= $cutoff;
    }));
    usort($sessions, fn(array $a, array $b): int => strcmp((string)$a['start'], (string)$b['start']));
    return $sessions;
}

// ---------------------------------------------------------------------------
// HTTP
// ---------------------------------------------------------------------------

function load_config(): array
{
    $defaults = [
        'ingest_token' => '',
        // Prefix of the User-Agent the sessions feed is served to. Empty serves everyone.
        'feed_user_agent_prefix' => 'stevekirtley-ha-edf-energy/',
        // Requests per address per window for the public actions.
        'rate_limit_requests' => 30,
        'rate_limit_window_seconds' => 300,
    ];
    $path = __DIR__ . '/config.php';
    if (is_file($path)) {
        $overrides = include $path;
        if (is_array($overrides)) {
            return array_merge($defaults, $overrides);
        }
    }
    return $defaults;
}

/** Whether this request may read the sessions feed: the integration's user agent, or the token. */
function feed_access_allowed(array $config): bool
{
    $prefix = (string)$config['feed_user_agent_prefix'];
    if ($prefix === '') {
        return true;
    }
    $agent = (string)($_SERVER['HTTP_USER_AGENT'] ?? '');
    if (strncmp($agent, $prefix, strlen($prefix)) === 0) {
        return true;
    }
    $expected = (string)$config['ingest_token'];
    $given = (string)($_SERVER['HTTP_X_TOKEN'] ?? $_GET['token'] ?? '');
    return $expected !== '' && hash_equals($expected, $given);
}

/** A fixed-window per-address rate limit; returns false once the window is exhausted. */
function within_rate_limit(array $config): bool
{
    $limit = (int)$config['rate_limit_requests'];
    $window = (int)$config['rate_limit_window_seconds'];
    if ($limit <= 0 || $window <= 0) {
        return true;
    }
    $address = (string)($_SERVER['REMOTE_ADDR'] ?? 'unknown');
    $path = cache_dir() . '/ratelimit_' . substr(sha1($address), 0, 16) . '.json';
    $state = read_json_file($path);
    $now = time();
    if (($state['window_start'] ?? 0) + $window <= $now) {
        $state = ['window_start' => $now, 'count' => 0];
    }
    $state['count'] = ($state['count'] ?? 0) + 1;
    try {
        write_json_file($path, $state);
    } catch (Throwable $e) {
        return true; // Never block on a bookkeeping failure.
    }
    return $state['count'] <= $limit;
}

function respond(int $status, array $body): void
{
    http_response_code($status);
    header('Content-Type: application/json');
    header('Cache-Control: no-store');
    header('Access-Control-Allow-Origin: *');
    echo json_encode($body, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE);
    exit;
}

function require_token(array $config): void
{
    $expected = (string)$config['ingest_token'];
    if ($expected === '') {
        respond(403, ['ok' => false, 'error' => 'ingest_token is not configured on the server']);
    }
    $given = (string)($_SERVER['HTTP_X_TOKEN'] ?? $_GET['token'] ?? '');
    if (!hash_equals($expected, $given)) {
        respond(401, ['ok' => false, 'error' => 'invalid token']);
    }
}

function request_body(): array
{
    $raw = (string)file_get_contents('php://input');
    $json = json_decode($raw, true);
    if (is_array($json)) {
        return $json;
    }
    return $_POST;
}

function parse_received_at(?string $value): DateTimeImmutable
{
    $tz = new DateTimeZone(TIMEZONE);
    if ($value !== null && trim($value) !== '') {
        try {
            return (new DateTimeImmutable($value))->setTimezone($tz);
        } catch (Exception $e) {
            // Fall through to "now".
        }
    }
    return new DateTimeImmutable('now', $tz);
}

function main(): void
{
    date_default_timezone_set(TIMEZONE);
    $config = load_config();
    $action = (string)($_GET['action'] ?? 'sessions');
    $now = new DateTimeImmutable('now', new DateTimeZone(TIMEZONE));

    switch ($action) {
        case 'health':
            respond(200, [
                'ok' => true,
                'ingest_enabled' => $config['ingest_token'] !== '',
                'cache_writable' => is_writable(cache_dir()) || (!is_dir(cache_dir()) && is_writable(__DIR__)),
                'messages' => count(read_json_file(messages_path())),
                'sessions' => count(build_sessions($now)),
                'time' => $now->format(DATE_ATOM),
            ]);
            // no break: respond() exits

        case 'sessions':
            if (!within_rate_limit($config)) {
                respond(429, ['ok' => false, 'error' => 'rate limited']);
            }
            if (!feed_access_allowed($config)) {
                respond(403, [
                    'ok' => false,
                    'error' => 'This feed is provided for the HomeAssistant-EDFEnergy integration '
                        . '(https://github.com/stevekirtley/HomeAssistant-EDFEnergy).',
                ]);
            }
            respond(200, [
                'generated_at' => $now->format(DATE_ATOM),
                'source' => 'power_perks',
                'sessions' => build_sessions($now),
            ]);
            // no break

        case 'parse':
            if (!within_rate_limit($config)) {
                respond(429, ['ok' => false, 'error' => 'rate limited']);
            }
            $text = (string)($_GET['text'] ?? request_body()['text'] ?? '');
            if ($text === '') {
                respond(400, ['ok' => false, 'error' => 'text is required']);
            }
            $received = parse_received_at($_GET['received_at'] ?? null);
            $parsed = parse_power_perks_message($text, $received);
            respond(200, [
                'ok' => !isset($parsed['error']),
                'received_at' => $received->format(DATE_ATOM),
                'session' => isset($parsed['error']) ? null : [
                    'code' => $parsed['code'],
                    'start' => $parsed['start']->format(DATE_ATOM),
                    'end' => $parsed['end']->format(DATE_ATOM),
                ],
                'error' => $parsed['error'] ?? null,
            ]);
            // no break

        case 'messages':
            require_token($config);
            respond(200, ['messages' => read_json_file(messages_path())]);
            // no break

        case 'ingest':
            require_token($config);
            if (($_SERVER['REQUEST_METHOD'] ?? 'GET') !== 'POST') {
                respond(405, ['ok' => false, 'error' => 'POST required']);
            }
            $body = request_body();
            $text = trim((string)($body['text'] ?? ''));
            if ($text === '') {
                respond(400, ['ok' => false, 'error' => 'text is required']);
            }
            $received = parse_received_at(isset($body['received_at']) ? (string)$body['received_at'] : null);
            $sender = (string)($body['sender'] ?? '');
            try {
                $record = ingest_message($text, $received, $sender);
            } catch (Throwable $e) {
                respond(500, ['ok' => false, 'error' => $e->getMessage()]);
            }
            respond(200, [
                'ok' => $record['session'] !== null,
                'duplicate' => !empty($record['duplicate']),
                'id' => $record['id'],
                'session' => $record['session'],
                'error' => $record['parse_error'],
            ]);
            // no break

        default:
            respond(404, ['ok' => false, 'error' => 'unknown action']);
    }
}

if (PHP_SAPI !== 'cli' || !defined('POWER_PERKS_NO_MAIN')) {
    main();
}
