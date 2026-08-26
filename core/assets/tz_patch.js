/* Lop va mui gio -- chay trong sandbox phu len window cua tung trang.
 *
 * Sandbox co bo built-in RIENG, nen moi thu can va deu phai lay qua `window`.
 * Gio cua vung dich duoc tinh bang chinh ICU cua trinh duyet
 * (Intl.DateTimeFormat voi timeZone chi dinh), nho vay DST luon dung ma khong
 * can nhung bang du lieu mui gio nao.
 *
 * Bien `TZ_NAME` do process script gan vao sandbox truoc khi nap file nay.
 */
"use strict";

(function () {
  var TZ = typeof TZ_NAME === "string" ? TZ_NAME : "";
  var W = typeof window !== "undefined" ? window : null;
  if (!TZ || !W || W.__tzShimApplied) { return; }

  var NativeDate = W.Date;
  var NativeIntl = W.Intl;
  if (!NativeDate || !NativeIntl || !NativeIntl.DateTimeFormat) { return; }

  var DP = NativeDate.prototype;
  var NativeDTF = NativeIntl.DateTimeFormat;

  // Giu ban goc truoc khi va, de dung noi bo ma khong bi de quy.
  var nGetTime = DP.getTime;
  var nSetTime = DP.setTime;
  var nGetTimezoneOffset = DP.getTimezoneOffset;
  var nToString = DP.toString;
  var nSetUTCFullYear = DP.setUTCFullYear;
  var nSetUTCHours = DP.setUTCHours;
  var nGetUTCDay = DP.getUTCDay;
  var nUTC = NativeDate.UTC;
  var nNow = NativeDate.now;
  var nParse = NativeDate.parse;

  var UTC_GETTERS = {
    FullYear: DP.getUTCFullYear,
    Month: DP.getUTCMonth,
    Date: DP.getUTCDate,
    Day: DP.getUTCDay,
    Hours: DP.getUTCHours,
    Minutes: DP.getUTCMinutes,
    Seconds: DP.getUTCSeconds,
    Milliseconds: DP.getUTCMilliseconds,
  };

  function rawDate(t) { return new NativeDate(t); }

  // --- che dau viec da va: Function.prototype.toString van bao [native code] ---
  var disguised = new WeakSet();
  function define(target, name, value) {
    if (typeof value === "function") { disguised.add(value); }
    try {
      Object.defineProperty(target, name, {
        value: value, writable: true, enumerable: false, configurable: true,
      });
    } catch (e) { /* thuoc tinh khong ghi de duoc thi bo qua */ }
  }

  // ------------------------------------------------------------------
  // Tinh gio cua vung dich
  // ------------------------------------------------------------------
  var offsetFmt = new NativeDTF("en-US", {
    timeZone: TZ, hourCycle: "h23",
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  });
  var nameFmt = new NativeDTF("en-US", { timeZone: TZ, timeZoneName: "long" });

  var offsetCache = new Map();

  /** Chenh lech phut so voi UTC, quy uoc giong getTimezoneOffset (duong = phia tay). */
  function offsetFor(t) {
    if (!isFinite(t)) { return NaN; }
    var key = Math.floor(t / 60000);
    var cached = offsetCache.get(key);
    if (cached !== undefined) { return cached; }

    var parts = offsetFmt.formatToParts(rawDate(t));
    var got = {};
    for (var i = 0; i < parts.length; i++) { got[parts[i].type] = parts[i].value; }
    var hour = parseInt(got.hour, 10);
    if (hour === 24) { hour = 0; }

    // Dung setUTCFullYear thay Date.UTC de khong dinh quy tac nam 2 chu so.
    var probe = rawDate(0);
    nSetUTCFullYear.call(probe, parseInt(got.year, 10),
                         parseInt(got.month, 10) - 1, parseInt(got.day, 10));
    nSetUTCHours.call(probe, hour, parseInt(got.minute, 10), parseInt(got.second, 10), 0);
    var offset = -Math.round((nGetTime.call(probe) - t) / 60000);

    if (offsetCache.size > 4096) { offsetCache.clear(); }
    offsetCache.set(key, offset);
    return offset;
  }

  /** Moc thoi gian -> so mili giay cua "dong ho treo tuong" tai vung dich. */
  function wallOf(t) { return t - offsetFor(t) * 60000; }

  /** Dong ho treo tuong -> moc thoi gian. Tinh hai lan cho dung quanh moc doi DST. */
  function instantOf(wall) {
    if (!isFinite(wall)) { return NaN; }
    var guess = offsetFor(wall);
    var t = wall + guess * 60000;
    var refined = offsetFor(t);
    if (refined !== guess) { t = wall + refined * 60000; }
    return t;
  }

  function wallParts(t) {
    var d = rawDate(wallOf(t));
    return [
      UTC_GETTERS.FullYear.call(d), UTC_GETTERS.Month.call(d), UTC_GETTERS.Date.call(d),
      UTC_GETTERS.Hours.call(d), UTC_GETTERS.Minutes.call(d),
      UTC_GETTERS.Seconds.call(d), UTC_GETTERS.Milliseconds.call(d),
    ];
  }

  function wallToMs(p) {
    var d = rawDate(0);
    nSetUTCFullYear.call(d, p[0], p[1], p[2]);
    nSetUTCHours.call(d, p[3], p[4], p[5], p[6]);
    return nGetTime.call(d);
  }

  // ------------------------------------------------------------------
  // Cac ham doc gio dia phuong
  // ------------------------------------------------------------------
  define(DP, "getTimezoneOffset", function getTimezoneOffset() {
    var t = nGetTime.call(this);
    return t !== t ? NaN : offsetFor(t);
  });

  ["FullYear", "Month", "Date", "Day", "Hours", "Minutes", "Seconds", "Milliseconds"]
    .forEach(function (field) {
      var read = UTC_GETTERS[field];
      define(DP, "get" + field, function () {
        var t = nGetTime.call(this);
        return t !== t ? NaN : read.call(rawDate(wallOf(t)));
      });
    });

  define(DP, "getYear", function getYear() {
    var t = nGetTime.call(this);
    return t !== t ? NaN : UTC_GETTERS.FullYear.call(rawDate(wallOf(t))) - 1900;
  });

  // ------------------------------------------------------------------
  // Cac ham dat gio dia phuong
  // ------------------------------------------------------------------
  var SETTERS = {
    setFullYear: 0, setMonth: 1, setDate: 2,
    setHours: 3, setMinutes: 4, setSeconds: 5, setMilliseconds: 6,
  };
  Object.keys(SETTERS).forEach(function (name) {
    var start = SETTERS[name];
    define(DP, name, function () {
      var t = nGetTime.call(this);
      var parts;
      if (t !== t) {
        // Theo chuan, chi setFullYear moi cuu duoc mot Date da NaN.
        if (name !== "setFullYear") { return NaN; }
        parts = [1970, 0, 1, 0, 0, 0, 0];
      } else {
        parts = wallParts(t);
      }
      var count = arguments.length;
      for (var i = 0; i < count && start + i < 7; i++) {
        parts[start + i] = Number(arguments[i]);
      }
      for (var k = 0; k < 7; k++) {
        if (!isFinite(parts[k])) { nSetTime.call(this, NaN); return NaN; }
      }
      return nSetTime.call(this, instantOf(wallToMs(parts)));
    });
  });

  define(DP, "setYear", function setYear(value) {
    var year = Number(value);
    if (year >= 0 && year <= 99) { year += 1900; }
    var t = nGetTime.call(this);
    var parts = t !== t ? [1970, 0, 1, 0, 0, 0, 0] : wallParts(t);
    parts[0] = year;
    return nSetTime.call(this, instantOf(wallToMs(parts)));
  });

  // ------------------------------------------------------------------
  // Cac ham doi ra chuoi
  // ------------------------------------------------------------------
  var WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  function pad(value, width) {
    var text = String(Math.abs(value));
    while (text.length < width) { text = "0" + text; }
    return text;
  }

  function zoneLongName(t) {
    var parts = nameFmt.formatToParts(rawDate(t));
    for (var i = 0; i < parts.length; i++) {
      if (parts[i].type === "timeZoneName") { return parts[i].value; }
    }
    return TZ;
  }

  function datePart(t) {
    var parts = wallParts(t);
    var weekday = nGetUTCDay.call(rawDate(wallOf(t)));
    var year = parts[0];
    var shown = year < 0 ? "-" + pad(year, 6) : pad(year, 4);
    return WEEKDAYS[weekday] + " " + MONTHS[parts[1]] + " " + pad(parts[2], 2) + " " + shown;
  }

  function timePart(t) {
    var parts = wallParts(t);
    var offset = offsetFor(t);
    var sign = offset > 0 ? "-" : "+";
    var abs = Math.abs(offset);
    return pad(parts[3], 2) + ":" + pad(parts[4], 2) + ":" + pad(parts[5], 2) +
           " GMT" + sign + pad(Math.floor(abs / 60), 2) + pad(abs % 60, 2) +
           " (" + zoneLongName(t) + ")";
  }

  define(DP, "toString", function toString() {
    var t = nGetTime.call(this);
    return t !== t ? "Invalid Date" : datePart(t) + " " + timePart(t);
  });
  define(DP, "toDateString", function toDateString() {
    var t = nGetTime.call(this);
    return t !== t ? "Invalid Date" : datePart(t);
  });
  define(DP, "toTimeString", function toTimeString() {
    var t = nGetTime.call(this);
    return t !== t ? "Invalid Date" : timePart(t);
  });

  function withZone(options, fallback) {
    var merged = {};
    var hasField = false;
    if (options !== undefined && options !== null) {
      for (var key in Object(options)) {
        merged[key] = Object(options)[key];
        if (key !== "timeZone" && key !== "localeMatcher" && key !== "hour12" &&
            key !== "hourCycle" && key !== "formatMatcher" && key !== "calendar" &&
            key !== "numberingSystem") {
          hasField = true;
        }
      }
    }
    if (!hasField) {
      for (var name in fallback) { merged[name] = fallback[name]; }
    }
    if (merged.timeZone === undefined) { merged.timeZone = TZ; }
    return merged;
  }

  var DATE_DEFAULTS = { year: "numeric", month: "numeric", day: "numeric" };
  var TIME_DEFAULTS = { hour: "numeric", minute: "numeric", second: "numeric" };
  var BOTH_DEFAULTS = {
    year: "numeric", month: "numeric", day: "numeric",
    hour: "numeric", minute: "numeric", second: "numeric",
  };

  function makeLocale(name, defaults) {
    define(DP, name, function (locales, options) {
      var t = nGetTime.call(this);
      if (t !== t) { return "Invalid Date"; }
      return new NativeDTF(locales, withZone(options, defaults)).format(rawDate(t));
    });
  }
  makeLocale("toLocaleString", BOTH_DEFAULTS);
  makeLocale("toLocaleDateString", DATE_DEFAULTS);
  makeLocale("toLocaleTimeString", TIME_DEFAULTS);

  // ------------------------------------------------------------------
  // Doc chuoi ngay gio
  // ------------------------------------------------------------------
  // Chuoi ISO co 'Z' hoac co chenh lech mui gio thi da xac dinh moc tuyet doi;
  // chuoi chi co ngay ("2024-01-15") theo chuan cung la UTC. Nhung dang con lai
  // duoc hieu theo gio dia phuong -> phai doc lai theo vung dich.
  var ABSOLUTE_ISO = /^\s*[+-]?\d{4,6}-\d{2}-\d{2}(?:$|[T ].*(?:Z|[+-]\d{2}:?\d{2})\s*$)/;

  function parseString(text) {
    var native = nParse.call(NativeDate, text);
    if (native !== native) { return NaN; }
    if (ABSOLUTE_ISO.test(text)) { return native; }
    // Doi tu gio may that sang gio vung dich, giu nguyen so tren dong ho.
    var machineOffset = nGetTimezoneOffset.call(rawDate(native));
    return instantOf(native - machineOffset * 60000);
  }

  // ------------------------------------------------------------------
  // Ham dung Date
  // ------------------------------------------------------------------
  function toPrimitive(value) {
    if (value === null || (typeof value !== "object" && typeof value !== "function")) {
      return value;
    }
    var exotic = value[Symbol.toPrimitive];
    if (exotic !== undefined && exotic !== null) { return exotic.call(value, "default"); }
    var primitive = value.valueOf ? value.valueOf() : value;
    if (primitive === null || typeof primitive !== "object") { return primitive; }
    return String(value);
  }

  function ShimDate(year, month, day, hours, minutes, seconds, ms) {
    if (new.target === undefined) { return nToString.call(rawDate(nNow())); }

    var count = arguments.length;
    var t;
    if (count === 0) {
      t = nNow();
    } else if (count === 1) {
      var only = arguments[0];
      if (only instanceof NativeDate) {
        t = nGetTime.call(only);
      } else {
        var primitive = toPrimitive(only);
        t = typeof primitive === "string" ? parseString(primitive) : Number(primitive);
      }
    } else {
      var parts = [Number(arguments[0]), Number(arguments[1]),
                   count > 2 ? Number(arguments[2]) : 1,
                   count > 3 ? Number(arguments[3]) : 0,
                   count > 4 ? Number(arguments[4]) : 0,
                   count > 5 ? Number(arguments[5]) : 0,
                   count > 6 ? Number(arguments[6]) : 0];
      if (parts[0] >= 0 && parts[0] <= 99) { parts[0] += 1900; }
      var ok = true;
      for (var i = 0; i < 7; i++) { if (!isFinite(parts[i])) { ok = false; } }
      t = ok ? instantOf(wallToMs(parts)) : NaN;
    }
    return Reflect.construct(NativeDate, [t], new.target);
  }

  ShimDate.prototype = DP;
  ShimDate.now = nNow;
  ShimDate.UTC = nUTC;
  define(ShimDate, "parse", function parse(text) { return parseString(String(text)); });
  Object.defineProperty(ShimDate, "name", { value: "Date", configurable: true });
  Object.defineProperty(ShimDate, "length", { value: 7, configurable: true });
  disguised.add(ShimDate);
  define(DP, "constructor", ShimDate);
  define(W, "Date", ShimDate);

  // ------------------------------------------------------------------
  // Intl.DateTimeFormat mac dinh dung vung dich
  // ------------------------------------------------------------------
  function ShimDateTimeFormat(locales, options) {
    var merged = {};
    if (options !== undefined && options !== null) {
      for (var key in Object(options)) { merged[key] = Object(options)[key]; }
    }
    if (merged.timeZone === undefined) { merged.timeZone = TZ; }
    return new NativeDTF(locales, merged);
  }
  ShimDateTimeFormat.prototype = NativeDTF.prototype;
  define(ShimDateTimeFormat, "supportedLocalesOf", function supportedLocalesOf(l, o) {
    return NativeDTF.supportedLocalesOf(l, o);
  });
  Object.defineProperty(ShimDateTimeFormat, "name", { value: "DateTimeFormat", configurable: true });
  Object.defineProperty(ShimDateTimeFormat, "length", { value: 0, configurable: true });
  disguised.add(ShimDateTimeFormat);
  define(NativeDTF.prototype, "constructor", ShimDateTimeFormat);
  define(NativeIntl, "DateTimeFormat", ShimDateTimeFormat);

  // ------------------------------------------------------------------
  // Temporal (Firefox 154 da bat san)
  // ------------------------------------------------------------------
  // Cac ham trong Temporal.Now lay mui gio he thong khi khong duoc truyen vao,
  // nen phai dat san vung dich lam mac dinh, neu khong la lo nguyen hinh.
  var Temporal = W.Temporal;
  if (Temporal && Temporal.Now) {
    var Now = Temporal.Now;
    if (typeof Now.timeZoneId === "function") {
      define(Now, "timeZoneId", function timeZoneId() { return TZ; });
    }
    ["plainDateTimeISO", "plainDateISO", "plainTimeISO", "zonedDateTimeISO"]
      .forEach(function (name) {
        var original = Now[name];
        if (typeof original !== "function") { return; }
        define(Now, name, function (timeZone) {
          return original.call(Now, timeZone === undefined ? TZ : timeZone);
        });
      });
  }

  // ------------------------------------------------------------------
  // Che dau dau vet cua lop va
  // ------------------------------------------------------------------
  var FP = W.Function.prototype;
  var nFnToString = FP.toString;
  define(FP, "toString", function toString() {
    if (disguised.has(this)) {
      return "function " + (this.name || "") + "() { [native code] }";
    }
    return nFnToString.call(this);
  });

  W.__tzShimApplied = true;
})();
