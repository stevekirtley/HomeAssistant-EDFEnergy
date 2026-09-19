<?php
/**
 * Parser tests for the Power Perks relay. Run with:  php tests.php
 *
 * Every case is a text EDF might send, the date it arrived, and the window it must produce
 * (local time). EDF reword their messages, so the cases cover the phrasings we can imagine
 * rather than just the one we have seen.
 */

declare(strict_types=1);

define('POWER_PERKS_NO_MAIN', true);
require __DIR__ . '/power_perks.php';

$tz = new DateTimeZone('Europe/London');
$received = new DateTimeImmutable('2026-09-18 10:15:00', $tz);   // a Friday

$cases = [
    // The real first message, verbatim.
    ["It's Power Perks time! Great news, you've got free electricity tomorrow, 19 September, between 4am-4pm. Enjoy.", '2026-09-19 04:00', '2026-09-19 16:00'],
    // Rewordings of the same session.
    ['Power Perks: free electricity tomorrow (Sat 19 Sept) from 4am to 4pm.', '2026-09-19 04:00', '2026-09-19 16:00'],
    ['POWER PERKS - free electricity on Saturday 19th September between 4am and 4pm', '2026-09-19 04:00', '2026-09-19 16:00'],
    ['Power Perks free electricity 19/09 04:00-16:00', '2026-09-19 04:00', '2026-09-19 16:00'],
    ['Your Power Perks event is tomorrow, September 19, 4 a.m. – 4 p.m.', '2026-09-19 04:00', '2026-09-19 16:00'],
    ['Power Perks tomorrow 4-4pm', '2026-09-19 04:00', '2026-09-19 16:00'],
    ['Power Perks tomorrow 4am-4', '2026-09-19 04:00', '2026-09-19 16:00'],
    // Relative dates only.
    ['Power Perks: free electricity today 1pm-3pm', '2026-09-18 13:00', '2026-09-18 15:00'],
    ['Power Perks this Sunday 10am until 2pm', '2026-09-20 10:00', '2026-09-20 14:00'],
    ['Power Perks on Friday 2pm to 5pm', '2026-09-18 14:00', '2026-09-18 17:00'],   // same weekday = today
    // Half hours, midday, midnight, and a window over midnight.
    ['Power Perks tomorrow 11.30am to 2.30pm', '2026-09-19 11:30', '2026-09-19 14:30'],
    ['Power Perks tomorrow midday-3pm', '2026-09-19 12:00', '2026-09-19 15:00'],
    ['Power Perks tomorrow noon to 4pm', '2026-09-19 12:00', '2026-09-19 16:00'],
    ['Power Perks tomorrow 10pm-2am', '2026-09-19 22:00', '2026-09-20 02:00'],
    ['Power Perks tomorrow 12am-4am', '2026-09-19 00:00', '2026-09-19 04:00'],
    ['Power Perks tomorrow 12pm-4pm', '2026-09-19 12:00', '2026-09-19 16:00'],
    // Explicit date takes priority over "tomorrow", and the year rolls over sensibly.
    ['Power Perks: free electricity tomorrow, 2 January, 4am-4pm', '2027-01-02 04:00', '2027-01-02 16:00', '2026-12-31 09:00:00'],
    ['Power Perks 19 September 2026 4am-4pm', '2026-09-19 04:00', '2026-09-19 16:00'],
    // Unicode dashes and messy spacing.
    ["Power Perks\n\nTomorrow 19 September\n4am — 4pm", '2026-09-19 04:00', '2026-09-19 16:00'],
];

$rejected = [
    // No mention of Power Perks: some other EDF text with a window in it.
    "Your Weekend Saver hours are booked for Saturday 4pm-6pm.",
    // Power Perks but nothing to schedule.
    "It's Power Perks time! You've joined. We'll text you the day before each event.",
    // Power Perks with a date but no window.
    'Power Perks: free electricity tomorrow 19 September. Enjoy!',
    // Impossible times.
    'Power Perks tomorrow 25am-4pm',
];

$failures = 0;
$total = 0;

foreach ($cases as $case) {
    [$text, $expectedStart, $expectedEnd] = $case;
    $at = isset($case[3]) ? new DateTimeImmutable($case[3], $tz) : $received;
    $total++;
    $result = parse_power_perks_message($text, $at);
    if (isset($result['error'])) {
        $failures++;
        echo "FAIL  {$text}\n      expected {$expectedStart} -> {$expectedEnd}, got error: {$result['error']}\n";
        continue;
    }
    $first = $result['sessions'][0];
    $gotStart = $first['start']->format('Y-m-d H:i');
    $gotEnd = $first['end']->format('Y-m-d H:i');
    if ($gotStart !== $expectedStart || $gotEnd !== $expectedEnd || count($result['sessions']) !== 1) {
        $failures++;
        echo "FAIL  {$text}\n      expected {$expectedStart} -> {$expectedEnd} (1 session), got {$gotStart} -> {$gotEnd} (" . count($result['sessions']) . ")\n";
        continue;
    }
    echo "ok    {$gotStart} -> {$gotEnd}  {$first['code']}\n";
}

foreach ($rejected as $text) {
    $total++;
    $result = parse_power_perks_message($text, $received);
    if (!isset($result['error'])) {
        $failures++;
        echo "FAIL  should have been rejected: {$text}\n      got " . count($result['sessions']) . " session(s)\n";
        continue;
    }
    echo "ok    rejected ({$result['error']}): " . substr($text, 0, 60) . "\n";
}

// Several windows over two days, as EDF actually sent on 19 September 2026.
$multi = [
    ["Great news, you've got Power Perks free electricity tonight, 19 September and tomorrow. Your free hours are 11pm-6am, 9am-2pm and 3pm-4pm. Enjoy.", '2026-09-19 10:40:00',
        [['2026-09-19 23:00', '2026-09-20 06:00'], ['2026-09-20 09:00', '2026-09-20 14:00'], ['2026-09-20 15:00', '2026-09-20 16:00']]],
    ['Power Perks tomorrow: 4am-8am and 1pm-4pm', '2026-09-18 10:00:00',
        [['2026-09-19 04:00', '2026-09-19 08:00'], ['2026-09-19 13:00', '2026-09-19 16:00']]],
    // Same-day windows written with "between ... and" for the first one.
    ['Power Perks today between 9am and 11am, then 2pm to 4pm', '2026-09-19 08:00:00',
        [['2026-09-19 09:00', '2026-09-19 11:00'], ['2026-09-19 14:00', '2026-09-19 16:00']]],
];
foreach ($multi as [$text, $at, $expected]) {
    $total++;
    $result = parse_power_perks_message($text, new DateTimeImmutable($at, $tz));
    $got = isset($result['error']) ? [] : array_map(fn($s) => [$s['start']->format('Y-m-d H:i'), $s['end']->format('Y-m-d H:i')], $result['sessions']);
    if ($got !== $expected) {
        $failures++;
        echo "FAIL  {$text}\n      expected " . json_encode($expected) . "\n      got      " . json_encode($got) . (isset($result['error']) ? " ({$result['error']})" : '') . "\n";
        continue;
    }
    echo "ok    " . count($got) . " sessions: " . json_encode($got) . "\n";
}

// Timezone: the session is published with the UK offset, so 4am in BST is 03:00Z.
$total++;
$result = parse_power_perks_message('Power Perks tomorrow 4am-4pm', $received);
$utc = $result['sessions'][0]['start']->setTimezone(new DateTimeZone('UTC'))->format('Y-m-d H:i');
if ($utc !== '2026-09-19 03:00') {
    $failures++;
    echo "FAIL  BST offset: expected 2026-09-19 03:00Z, got {$utc}Z\n";
} else {
    echo "ok    BST offset: 4am local = {$utc}Z\n";
}

echo "\n" . ($total - $failures) . "/{$total} passed\n";
exit($failures === 0 ? 0 : 1);
