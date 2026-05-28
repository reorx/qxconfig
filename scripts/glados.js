/****************************** 
脚本功能：GLaDOS / Railgun 自动签到 + 积分兑换（多账号版）
更新时间：2026-05-28
使用说明：访问 GLaDOS 任意域名的 /console/account 页面抓包保存 Cookie，定时任务自动对已保存 Cookie 的域名执行签到。
         支持 glados.network、railgun.info、glados.vip，各域名支持多账号。
         同一域名多次抓包可保存不同账号的 Cookie。

[rewrite_local]
^https:\/\/glados\.network\/console\/account$ url script-request-header https://raw.githubusercontent.com/curtinp118/QuantumultX/refs/heads/main/scripts/glados.js
^https:\/\/railgun\.info\/console\/account$ url script-request-header https://raw.githubusercontent.com/curtinp118/QuantumultX/refs/heads/main/scripts/glados.js
^https:\/\/glados\.vip\/console\/account$ url script-request-header https://raw.githubusercontent.com/curtinp118/QuantumultX/refs/heads/main/scripts/glados.js

[task_local]
10 7 * * * https://raw.githubusercontent.com/curtinp118/QuantumultX/refs/heads/main/scripts/glados.js, tag=GLaDOS 签到, enabled=true

[MITM]
hostname = %APPEND% glados.network, railgun.info, glados.vip
*******************************/

const COOKIES_KEY_PREFIX = "GLaDOS_Cookies";
const DOMAINS_LIST_KEY = "GLaDOS_Domains";
const DOMAINS = ["glados.network", "railgun.info", "glados.vip"];
const EXCHANGE_PLAN = "plan500";
const UA =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36";
const isGetHeader = typeof $request !== "undefined";

function safeJsonParse(str) {
  try {
    return JSON.parse(str);
  } catch (_) {
    return null;
  }
}

// ─── Storage: per-domain cookie array ───

function cookiesKeyFor(domain) {
  return `${COOKIES_KEY_PREFIX}:${domain}`;
}

function getSavedDomains() {
  try {
    if (typeof $prefs === "undefined") return [];
    const raw = $prefs.valueForKey(DOMAINS_LIST_KEY);
    if (!raw) return [];
    const list = safeJsonParse(raw) || [];
    return Array.isArray(list) ? list.filter(Boolean) : [];
  } catch (e) {
    console.log("[GLaDOS] Error reading domains:", e);
    return [];
  }
}

function addDomain(domain) {
  try {
    if (typeof $prefs === "undefined") return;
    const list = getSavedDomains();
    if (!list.includes(domain)) {
      list.push(domain);
      $prefs.setValueForKey(JSON.stringify(list), DOMAINS_LIST_KEY);
    }
  } catch (e) {
    console.log("[GLaDOS] Error adding domain:", e);
  }
}

function getCookiesForDomain(domain) {
  try {
    if (typeof $prefs === "undefined") return [];
    const raw = $prefs.valueForKey(cookiesKeyFor(domain));
    if (!raw) return [];
    const list = safeJsonParse(raw);
    return Array.isArray(list) ? list.filter(Boolean) : [];
  } catch (e) {
    console.log("[GLaDOS] Error reading cookies:", e);
    return [];
  }
}

function saveCookie(domain, cookie) {
  try {
    if (typeof $prefs === "undefined" || !cookie)
      return { isNew: false, index: -1 };
    const cookies = getCookiesForDomain(domain);
    const existingIdx = cookies.indexOf(cookie);
    if (existingIdx !== -1) {
      return { isNew: false, index: existingIdx };
    }
    cookies.push(cookie);
    $prefs.setValueForKey(JSON.stringify(cookies), cookiesKeyFor(domain));
    addDomain(domain);
    return { isNew: true, index: cookies.length - 1 };
  } catch (e) {
    console.log("[GLaDOS] Error saving cookie:", e);
    return { isNew: false, index: -1 };
  }
}

// ─── Helpers ───

function notify(title, subtitle, body) {
  $notify(title, subtitle, body);
}

function getHostFromRequest() {
  const h = ($request && $request.headers) || {};
  return h.Host || h.host || "";
}

function request(url, method, cookie, domain, body) {
  const headers = {
    "Content-Type": "application/json;charset=UTF-8",
    Origin: `https://${domain}`,
    Referer: `https://${domain}/console/current`,
    "User-Agent": UA,
    Cookie: cookie,
  };

  const opts = { url, method, headers };
  if (body !== undefined)
    opts.body = typeof body === "string" ? body : JSON.stringify(body);

  return $task.fetch(opts).then(
    (resp) => {
      const statusCode = resp.statusCode;
      const respBody = resp.body || "";
      const data = safeJsonParse(respBody);
      return { statusCode, data, raw: respBody };
    },
    (reason) => {
      const err = reason?.error
        ? String(reason.error)
        : String(reason || "Network error");
      return { statusCode: 0, data: null, raw: "", error: err };
    }
  );
}

// ─── API ───

async function checkin(cookie, domain) {
  const url = `https://${domain}/api/user/checkin`;
  const body = { token: domain };
  const { statusCode, data, raw, error } = await request(
    url, "POST", cookie, domain, body
  );

  if (error) {
    console.log(`[GLaDOS] ✗ 签到网络错误 [${domain}]: ${error}`);
    return { status: "签到失败", code: -2, message: error, points: "0" };
  }
  if (!data) {
    console.log(`[GLaDOS] ✗ 签到响应解析失败 [${domain}]: ${raw}`);
    return { status: "签到失败", code: -2, message: raw, points: "0" };
  }

  const code = data.code ?? -2;
  const message = data.message || "";
  const points = String(data.points ?? 0);

  if (code === 0) {
    console.log(`[GLaDOS] ✅ 签到成功 [${domain}]: +${points} 积分, ${message}`);
    return { status: "签到成功", code: 0, message, points };
  } else if (code === 1) {
    console.log(`[GLaDOS] 🔄 重复签到 [${domain}]: ${message}`);
    return { status: "重复签到", code: 1, message, points: "0" };
  } else {
    console.log(`[GLaDOS] ❌ 签到失败 [${domain}]: code=${code}, ${message}`);
    return { status: "签到失败", code, message, points: "0" };
  }
}

async function getStatus(cookie, domain) {
  const url = `https://${domain}/api/user/status`;
  const { statusCode, data, raw, error } = await request(
    url, "GET", cookie, domain
  );

  if (error || !data) {
    console.log(`[GLaDOS] ✗ 查询状态失败 [${domain}]: ${error || raw}`);
    return { leftDays: "N/A" };
  }

  const leftDays = data.data?.leftDays;
  if (leftDays !== undefined && leftDays !== null) {
    const days = parseInt(parseFloat(leftDays), 10);
    console.log(`[GLaDOS] 📊 剩余天数 [${domain}]: ${days} 天`);
    return { leftDays: `${days} 天` };
  }

  console.log(`[GLaDOS] 📊 状态响应 [${domain}]:`, JSON.stringify(data));
  return { leftDays: "N/A" };
}

async function getPoints(cookie, domain) {
  const url = `https://${domain}/api/user/points`;
  const { statusCode, data, raw, error } = await request(
    url, "GET", cookie, domain
  );

  if (error || !data) {
    console.log(`[GLaDOS] ✗ 查询积分失败 [${domain}]: ${error || raw}`);
    return { points: "N/A", pointsNum: 0 };
  }

  const points = data.points;
  if (points !== undefined && points !== null) {
    const pointsInt = parseInt(parseFloat(points), 10);
    console.log(`[GLaDOS] 💰 总积分 [${domain}]: ${pointsInt}`);
    return { points: `${pointsInt}`, pointsNum: pointsInt };
  }

  console.log(`[GLaDOS] 💰 积分响应 [${domain}]:`, JSON.stringify(data));
  return { points: "N/A", pointsNum: 0 };
}

async function exchange(cookie, domain, plan) {
  const url = `https://${domain}/api/user/exchange`;
  const body = { planType: plan };
  const { statusCode, data, raw, error } = await request(
    url, "POST", cookie, domain, body
  );

  if (error || !data) {
    console.log(`[GLaDOS] ✗ 兑换失败 [${domain}]: ${error || raw}`);
    return `兑换失败: ${error || raw}`;
  }

  const code = data.code ?? -2;
  const message = data.message || "";

  if (code === 0) {
    console.log(`[GLaDOS] 🎁 兑换成功 [${domain}]: ${plan}, ${message}`);
    return `兑换成功(${plan})`;
  } else {
    console.log(`[GLaDOS] ❌ 兑换失败 [${domain}]: code=${code}, ${message}`);
    return `兑换失败: ${message}`;
  }
}

async function checkinForAccount(cookie, domain, accountLabel) {
  console.log(`[GLaDOS] ── ${accountLabel} | ${domain} ──`);

  const statusBefore = await getStatus(cookie, domain);
  const checkinResult = await checkin(cookie, domain);
  const pointsResult = await getPoints(cookie, domain);
  let exchangeResult = "跳过(积分不足)";
  if (pointsResult.pointsNum >= 500) {
    exchangeResult = await exchange(cookie, domain, EXCHANGE_PLAN);
  } else {
    console.log(`[GLaDOS] 积分 ${pointsResult.pointsNum} < 500，跳过兑换`);
  }
  const statusAfter = await getStatus(cookie, domain);

  return {
    accountLabel,
    domain,
    status: checkinResult.status,
    code: checkinResult.code,
    message: checkinResult.message,
    earnedPoints: checkinResult.points,
    totalPoints: pointsResult.points,
    daysBefore: statusBefore.leftDays,
    daysAfter: statusAfter.leftDays,
    exchange: exchangeResult,
  };
}

// ─── Main ───

if (isGetHeader) {
  const allHeaders = $request.headers || {};
  const cookie = allHeaders.Cookie || allHeaders.cookie || "";
  const host = getHostFromRequest();

  if (!cookie || !host) {
    console.log("[GLaDOS] Cookie or Host not found in request headers");
    notify("GLaDOS", "抓包失败", "未获取到 Cookie 或 Host，请检查重写配置");
    $done({});
  } else {
    const { isNew, index } = saveCookie(host, cookie);
    const label = `账号 #${index + 1}`;
    if (isNew) {
      console.log(`[GLaDOS] ${label} Cookie saved for ${host}`);
      notify("GLaDOS", `${label} 已保存 [${host}]`, "新账号 Cookie 已记录，将用于自动签到");
    } else {
      console.log(`[GLaDOS] ${label} Cookie already exists for ${host}`);
      notify("GLaDOS", `${label} 已存在 [${host}]`, "该 Cookie 已保存过，无需重复抓包");
    }
    $done({});
  }
} else {
  const delay = Math.floor(Math.random() * 11);
  console.log(`[GLaDOS] 随机延迟 ${delay}s`);
  setTimeout(async () => {
    const savedDomains = getSavedDomains();

    if (savedDomains.length === 0) {
      console.log("[GLaDOS] 未找到已保存的 Cookie");
      $notify("GLaDOS 签到", "无 Cookie", "请先访问 /console/account 抓包");
      return $done();
    }

    const allResults = [];
    let totalAccounts = 0;

    for (const domain of savedDomains) {
      const cookies = getCookiesForDomain(domain);
      if (cookies.length === 0) {
        console.log(`[GLaDOS] ⚠️ ${domain} 无 Cookie，跳过`);
        continue;
      }
      for (let i = 0; i < cookies.length; i++) {
        totalAccounts++;
        const label = `账号 #${i + 1}`;
        console.log(`[GLaDOS] ═══ ${label} | ${domain} ═══`);
        allResults.push(await checkinForAccount(cookies[i], domain, label));
      }
    }

    console.log(`[GLaDOS] 🚀 共 ${totalAccounts} 个账号`);

    const ok = allResults.filter((r) => r.code === 0).length;
    const dup = allResults.filter((r) => r.code === 1).length;
    const fail = allResults.filter((r) => r.code !== 0 && r.code !== 1).length;

    const lines = allResults.map((r) => {
      const icon = r.code === 0 ? "✅" : r.code === 1 ? "🔄" : "❌";
      const pts = r.earnedPoints !== "0" ? ` +${r.earnedPoints}` : "";
      return `${icon} ${r.accountLabel} ${r.domain} | ${r.status}${pts} | ${r.daysBefore}→${r.daysAfter} | ${r.totalPoints}积分`;
    });

    const title = `GLaDOS | ${totalAccounts}账号 成${ok} 重${dup} 败${fail}`;
    const content = lines.join("\n");

    console.log(`\n[GLaDOS] ═══ 签到结果 ═══\n${content}\n`);
    $notify(title, "", content);
    $done();
  }, delay * 1000);
}
