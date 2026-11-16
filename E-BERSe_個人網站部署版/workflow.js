"use strict";

const kinds = {
  water: "水冷式冰水機", air: "氣冷式冰水機", vrf: "多聯變頻空調",
  unit: "其他空調主機", fund: "冰水泵", cond: "冷卻水泵", tower: "冷卻水塔",
  ahu: "空調箱", fcu: "風機盤管", other: "待分類／其他"
};
const fields = [
  ["kind", "設備類別", kinds], ["name", "設備編號／型號"], ["group", "所屬系統編號"],
  ["count", "確認台數", "number"], ["capacity", "額定冷房能力（單機）", "number"],
  ["unit", "冷房能力單位", {kW:"kW", W:"W", USRT:"USRT", "BTU/h":"BTU/h"}],
  ["power", "輸入功率（單機 kW）", "number"], ["efficiency", "銘牌效率及單位"],
  ["flow", "設計風量／水量及單位"], ["year", "出廠年"], ["grade", "銘牌能效等級"],
  ["inverter", "變頻證明"], ["refrigerant", "冷媒"], ["sources", "佐證照片編號"],
  ["visual", "散熱現況（專家勾選）", {poor:"極差", fair:"不佳", good:"合格"}],
  ["condensing", "冷媒冷凝溫度（°C）", "number"],
  ["outlet", "冷卻水出水溫度（°C）", "number"],
  ["operation", "水冷主機查驗狀態", {running:"運轉中", offline:"無法開機"}],
  ["evidence", "銘牌原文、讀值來源或現況說明", "textarea"]
];
const host = new Set(["water", "air", "vrf", "unit"]);
const factors = {kW:1, W:0.001, USRT:3.516, "BTU/h":0.000293071};
const visualFactors = {poor:0.8, fair:0.9, good:1};
let photos = [], devices = [], sources = [], notes = "";

function number(value) {
  if (value === null || value === undefined || String(value).trim() === "") return null;
  const result = Number(value);
  return Number.isFinite(result) ? result : null;
}

function assess(device) {
  const capacity = number(device.capacity);
  const kw = capacity > 0 && factors[device.unit] ? capacity * factors[device.unit] : null;
  if (!host.has(device.kind)) return {classification:"附屬設備／待分類", kw};
  const classification = kw === null ? "待確認" : kw > 10 ? "中央型" : "個別型";
  const visual = visualFactors[device.visual] ?? null;
  let approach = null, condensation = null, status = "";
  if (device.kind === "water") {
    const condensing = number(device.condensing), outlet = number(device.outlet);
    if (device.operation === "offline") status = "不判斷";
    else if (device.operation !== "running" || condensing === null || outlet === null) status = "須確認運轉狀態及兩項溫度";
    else {
      approach = Math.round((condensing - outlet) * 1000) / 1000;
      if (approach >= 0 && approach <= 3) condensation = 1;
      else if (approach >= 4 && approach <= 5) condensation = 0.9;
      else if (approach > 6) condensation = 0.8;
      if (condensation === null) status = "依原始讀值由專家確認判級";
    }
  }
  const power = number(device.power);
  const cop = kw !== null && power > 0 ? kw / power : null;
  const correctedCOP = device.kind === "air" && cop !== null && visual !== null ? cop * visual
    : device.kind === "water" && cop !== null && visual !== null && condensation !== null ? cop * visual * condensation
    : null;
  return {classification, kw, visual, approach, condensation, status, cop, correctedCOP};
}

function workbookRoute(devices, complete) {
  const mains = devices.filter(item => host.has(item.kind));
  const central = mains.filter(item => assess(item).classification === "中央型");
  const unresolved = !complete || !mains.length || devices.some(item => !item.kind || item.kind === "other") ||
    mains.some(item => assess(item).classification === "待確認") ||
    central.some(item => !Number.isInteger(number(item.count)) || number(item.count) <= 0);
  const total = unresolved ? null : central.reduce((sum, item) => sum + assess(item).kw * number(item.count) / 3.516, 0);
  let route = "待確認設備清冊、容量與台數";
  if (total !== null) {
    if (!central.length) route = "個別空調採表6";
    else if (Math.abs(total - 50) < 1e-8) route = "總容量恰為 50 USRT，請確認適用計算法";
    else if (total < 50) route = "中央空調總容量小於 50 USRT，採表5";
    else route = "中央空調總容量大於 50 USRT，採中央空調計算法";
    if (central.length && mains.some(item => assess(item).classification === "個別型")) route += "，個別空調另列入表6";
  }
  return {total, route};
}

if (typeof module !== "undefined") module.exports = {assess, workbookRoute};
else window.addEventListener("DOMContentLoaded", start);

function start() {
  const get = id => document.getElementById(id);
  const make = (tag, content) => {
    const node = document.createElement(tag);
    if (content !== undefined) node.textContent = content;
    return node;
  };
  const fmt = value => value === null || value === undefined ? "待確認" : Number(value.toFixed(3)).toString();
  const percent = value => value === null ? "待確認" : (value * 100).toFixed(0) + "%";
  function summary() {
    const {total, route} = workbookRoute(devices, get("complete").checked);
    get("route").textContent = route + (total === null ? "" : "。中央主機合計 " + fmt(total) + " USRT。");
    for (const [index, device] of devices.entries()) {
      const result = assess(device);
      const card = get("devices").children[index];
      const hints = [];
      if (host.has(device.kind)) {
        hints.push(result.classification + " · 單機 " + fmt(result.kw) + " kW");
        hints.push("散熱目視修正 " + percent(result.visual));
      }
      if (device.kind === "water") {
        if (result.approach !== null) hints.push("冷凝趨近溫度 " + fmt(result.approach) + " °C");
        if (result.status) hints.push(result.status);
        if (result.condensation !== null) hints.push("冷凝修正 " + percent(result.condensation));
      }
      if (result.correctedCOP !== null && result.correctedCOP !== undefined) hints.push("容量／輸入功率換算修正後 COP " + fmt(result.correctedCOP));
      card.querySelector("output").textContent = hints.join(" ｜ ");
    }
  }
  function render() {
    get("devices").replaceChildren();
    devices.forEach((device, index) => {
      const card = make("section"), header = make("div"), grid = make("div");
      card.className = "card"; header.className = "row"; grid.className = "grid";
      const remove = make("button", "移除"); remove.className = "light";
      remove.onclick = () => {devices.splice(index, 1); get("complete").checked = false; render();};
      header.append(make("h3", "設備 " + (index + 1)), remove);
      for (const [key, title, type] of fields) {
        const label = make("label", title);
        let input;
        if (type && typeof type === "object") {
          input = make("select");
          input.add(new Option("待確認", ""));
          for (const [value, caption] of Object.entries(type)) input.add(new Option(caption, value));
        } else {
          input = make(type === "textarea" ? "textarea" : "input");
          if (type === "number") { input.type = "number"; input.step = "any"; }
          if (type === "textarea") label.className = "wide";
        }
        input.value = device[key] ?? "";
        input.addEventListener("input", () => {
          device[key] = input.value;
          if (["kind", "count", "capacity", "unit"].includes(key)) get("complete").checked = false;
          summary();
        });
        label.append(input); grid.append(label);
      }
      card.append(header, grid, make("output")); get("devices").append(card);
    });
    summary();
  }
  function displaySources() {
    get("sources").textContent = sources.map(({id, name}) => id + " · " + name).join("\n");
    get("notes").textContent = notes;
  }
  get("complete").onchange = summary;
  get("add").onclick = () => {devices.push({}); get("complete").checked = false; render();};
  get("photos").onchange = event => {
    photos = Array.from(event.target.files);
    const preview = get("preview");
    for (const img of preview.querySelectorAll("img")) URL.revokeObjectURL(img.src);
    preview.replaceChildren();
    for (const photo of photos) {
      const figure = make("figure"), img = make("img");
      img.src = URL.createObjectURL(photo); img.alt = photo.name;
      figure.append(img, make("figcaption", photo.name)); preview.append(figure);
    }
  };
  get("scan").onclick = async () => {
    const status = get("status");
    if (!photos.length || photos.length > 12 || photos.some(p => p.size > 6000000) ||
        photos.reduce((n,p) => n + p.size,0) > 18000000) {
      status.textContent = "每批請選 1 至 12 張照片，單張限 6 MB，合計限 18 MB。"; return;
    }
    get("scan").disabled = true;
    get("load").disabled = true;
    get("loadDraft").disabled = get("saveDraft").disabled = true;
    const batch = [...photos];
    status.textContent = "辨識中，請稍候。";
    try {
      const input = await Promise.all(batch.map(photo => new Promise((resolve,reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve({mime: photo.type, data: reader.result.split(",")[1]});
        reader.onerror = reject;
        reader.readAsDataURL(photo);
      })));
      const response = await fetch("/recognize", {
        method:"POST", headers:{"Content-Type":"application/json", "X-Local-Token":document.body.dataset.token},
        body:JSON.stringify(input)
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error);
      const offset = sources.reduce((max, item) => Math.max(max, item.id), 0);
      for (let i=0; i<batch.length; i++) sources.push({id:offset+i+1, name:batch[i].name});
      const extracted = result.devices.filter(entry => entry && typeof entry === "object").map(entry => {
        const item = {};
        for (const [key] of fields) {
          if (!["visual","condensing","outlet","operation","group"].includes(key) &&
              ["string","number"].includes(typeof entry[key])) item[key] = String(entry[key]).slice(0,2000);
        }
        item.sources = String(item.sources || "").split(",").map(number)
          .filter(n => Number.isInteger(n) && n >= 1 && n <= batch.length).map(n => n + offset).join(",");
        return item;
      });
      devices.push(...extracted);
      notes = [notes, typeof result.notes === "string" ? result.notes : ""].filter(Boolean).join("\n");
      get("complete").checked = false;
      status.textContent = "本批新增 " + extracted.length + " 筆候選設備。請核對銘牌、台數與重複項。";
      displaySources(); render();
    } catch (error) {
      status.textContent = error.message || "辨識失敗，請重新嘗試。";
    } finally {get("scan").disabled = false; get("load").disabled = false; get("loadDraft").disabled = get("saveDraft").disabled = false;}
  };
  function caseData() {
    return {version:1, project:get("project").value, date:get("date").value, floors:get("floors").value,
      complete:get("complete").checked, sources, notes, observations:get("observations").value,
      devices:devices.map(item => ({...item, assessment:assess(item)})),
      routing:workbookRoute(devices,get("complete").checked)};
  }
  function download(blob, name) {
    const url = URL.createObjectURL(blob);
    const link = make("a"); link.href = url; link.download = name;
    link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  get("save").onclick = () => {
    const data = caseData();
    download(new Blob([JSON.stringify(data,null,2)], {type:"application/json"}), (data.date || "未填日期") + "_空調現勘.json");
  };
  get("report").onclick = async () => {
    const data = caseData();
    const status = get("exportStatus");
    const link = get("reportDownload");
    if (link.hasAttribute("href")) URL.revokeObjectURL(link.href);
    link.removeAttribute("href");
    link.hidden = true;
    get("report").disabled = true;
    status.textContent = "正在填入 Excel 範本。";
    try {
      const response = await fetch("/report", {
        method:"POST", headers:{"Content-Type":"application/json", "X-Local-Token":document.body.dataset.token},
        body:JSON.stringify(data)
      });
      if (!response.ok) {
        const details = await response.json().catch(() => ({}));
        throw new Error(details.error || "Excel 匯出失敗（HTTP " + response.status + "）。請重新開啟程式頁面後再試。");
      }
      if (!response.headers.get("Content-Type")?.includes("spreadsheetml.sheet")) {
        throw new Error("程式未回傳 Excel 檔。請重新開啟網站後再試。");
      }
      link.href = URL.createObjectURL(await response.blob());
      link.download = (data.date || "未填日期").replace(/-/g, "") + "_計算表2024 E-BERSe版v4.xlsx";
      link.hidden = false;
      status.textContent = "Excel 已產生。若瀏覽器未自動下載，請點下方連結。";
      link.click();
    } catch(error) {
      status.textContent = error.name === "TypeError"
        ? "無法連線到網站。請確認網站服務在線，重新整理頁面後再試。"
        : error.message || "匯出失敗，請重試。";
    } finally { get("report").disabled = false; }
  };
  let baseline;
  function applyCase(data) {
    if (!data || data.version !== 1 || !Array.isArray(data.devices) || !Array.isArray(data.sources) ||
        !data.devices.every(item => item && typeof item === "object") ||
        !data.sources.every(item => item && Number.isInteger(item.id) && item.id > 0 && typeof item.name === "string")) throw new Error();
    devices = data.devices.map(item => Object.fromEntries(fields.map(([key]) => [key,item[key]])));
    sources = data.sources;
    notes = typeof data.notes === "string" ? data.notes : "";
    get("project").value = data.project || ""; get("date").value = data.date || "";
    get("floors").value = data.floors || ""; get("observations").value = data.observations || ""; get("complete").checked = data.complete === true;
    get("photos").value = ""; get("photos").dispatchEvent(new Event("change"));
    displaySources(); render();
    baseline = JSON.stringify(caseData());
  }
  get("load").onchange = async event => {
    const file = event.target.files[0];
    if (!file) return;
    try {
      if (file.size > 3_000_000) throw new Error();
      applyCase(JSON.parse(await file.text()));
      get("status").textContent = "已載入案件。";
    } catch {get("status").textContent = "無法載入，請選擇本程式產出的案件 JSON。";}
    finally {event.target.value = "";}
  };
  async function useDraft(save) {
    const status = get("draftStatus");
    const before = JSON.stringify(caseData());
    const headers = {"X-Local-Token": document.body.dataset.token};
    get("saveDraft").disabled = get("loadDraft").disabled = get("scan").disabled = true;
    status.textContent = save ? "正在儲存案件。" : "正在讀取案件。";
    try {
      const response = await fetch("/draft", save
        ? {method: "POST", headers: {...headers, "Content-Type": "application/json"}, body: before}
        : {headers});
      const result = await response.json();
      if (!response.ok) throw new Error(result.error);
      if (save) {
        baseline = before;
        status.textContent = "已儲存案件。";
      } else {
        if (JSON.stringify(caseData()) !== baseline && !window.confirm("目前頁面有未儲存的變更。要載入上次儲存的案件嗎？")) {
          status.textContent = "已取消載入。";
          return;
        }
        applyCase(result);
        status.textContent = "已載入上次儲存的案件。";
      }
    } catch (error) {
      status.textContent = error.message || "案件操作失敗，請重試。";
    } finally {
      get("saveDraft").disabled = get("loadDraft").disabled = get("scan").disabled = false;
    }
  }
  get("saveDraft").onclick = () => useDraft(true);
  get("loadDraft").onclick = () => useDraft(false);
  get("date").value = new Intl.DateTimeFormat("sv-SE", {timeZone:"Asia/Taipei"}).format(new Date());
  render();
  baseline = JSON.stringify(caseData());
}
