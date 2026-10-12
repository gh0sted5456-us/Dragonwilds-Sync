// lib/apihelp.js
const { NextResponse } = require("next/server");

function ok(data) { return NextResponse.json({ ok: true, ...data }); }
function fail(message, status = 400) { return NextResponse.json({ ok: false, error: message }, { status }); }

module.exports = { ok, fail };
