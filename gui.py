import tkinter as tk
from tkinter import scrolledtext, messagebox, ttk
import requests
import re
import threading
import time

# ================= 核心逻辑类 =================
class AccurateIdSubmitter:
    def __init__(self, user_code, cookie, log_widget):
        self.user_code = user_code
        self.base_cookie = cookie
        self.log_widget = log_widget
        self.base_url = "http://gwxt.sgcc.com.cn/www/command"
        
        self.session = requests.Session()
        # 严格对齐你提供的 cURL Headers
        self.headers = {
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36 Edg/90.0.818.66',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6'
        }
        self._inject_cookie(self.base_cookie)

    def log(self, message):
        self.log_widget.insert(tk.END, message + "\n")
        self.log_widget.see(tk.END)
        self.log_widget.update_idletasks()

    def _inject_cookie(self, cookie_str):
        # 兼容处理 bkid=...; JSESSIONID2=... 格式
        for item in cookie_str.split(';'):
            if '=' in item:
                k, v = item.strip().split('=', 1)
                self.session.cookies.set(k, v)

    def run_single_course(self, leid, name):
        self.log(f"\n>>>> 处理: 【{name}】 (ID: {leid})")
        # 1. 选课确认
        self.session.post(f"{self.base_url}/XYxkzxControl?flag=chooseLesson_sysc",
            headers={**self.headers, 'Content-Type': 'application/x-www-form-urlencoded'},
            data={'leid': leid, 'category': '1', 'seled': '1'}, timeout=20)
        
        # 2. 嗅探资源 ID
        study_url = f"{self.base_url}/LessonAction?flag=study&le_id={leid}&type=4&preview=1&lessontype=1&source=null"
        res = self.session.get(study_url, headers=self.headers, timeout=20)
        match = re.search(r'([a-f0-9]{16})', res.text)
        resource_id = match.group(1) if match else "090f1b31c6496f4d"
        
        self.session.cookies.set(f"{self.user_code}{resource_id}", "1")
        
        # 3. 进度汇报
        play_ref = f"http://gwxt.sgcc.com.cn/www/jsp/normalCourse/play.jsp?le_id={leid}&preview=1&us_id={self.user_code}&source=null"
        params = {'flag': 'updateNormalStudyInfo', 'percentNum': '1', 'leid': leid, 'userCode': self.user_code, 'preview': '1', 'source': 'null'}
        self.session.post(f"{self.base_url}/LessonAction", params=params, headers={**self.headers, 'Referer': play_ref}, timeout=20)
        
        # 4. 成绩同步
        post_headers = {**self.headers, 'Referer': play_ref, 'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'}
        self.session.post(f"{self.base_url}/XYxkzxControl?flag=getIfDafen", data={'leid': leid}, headers=post_headers, timeout=20)
        self.session.post(f"{self.base_url}/CollegeControl?flag=lessonScore", data={'leid': leid}, headers=post_headers, timeout=20)
        self.log(f"    [OK] 任务完成")

    # ---------- MOOC 模式（新增） ----------
    def start_mooc_train(self, input_url):
        self.log("[*] 模式：MOOC 模式 (正在处理嵌套页面...)")
        
        # 核心修复：转换容器 URL 为真实内容 URL
        if "flag=topic_study" in input_url and "flag=topic_study_area" not in input_url:
            input_url = input_url.replace("flag=topic_study", "flag=topic_study_area")
            self.log("[修正] 检测到容器页面，已自动转向内容源地址")

        all_unique_ids = []
        current_page = 1
        total_pages = 1

        while current_page <= total_pages:
            # 清理 URL 参数，重新构造分页请求
            base_url = input_url.split('&pageNo=')[0].split('&pageSize=')[0]
            fetch_url = f"{base_url}&pageNo={current_page}&pageSize=10"
            self.log(f"[*] 正在拉取第 {current_page} 页: {fetch_url}")
            
            try:
                res = self.session.get(fetch_url, headers=self.headers, timeout=30)
                html_content = res.text

                # 1. 解析总页数 (countPageHID)
                if current_page == 1:
                    cp_match = re.search(r'id=["\']countPageHID["\']\s+value=["\'](\d+)["\']', html_content)
                    if cp_match:
                        total_pages = int(cp_match.group(1))
                        self.log(f"[*] 检测到总页数: {total_pages}")

                # 2. 提取课程 ID 
                # 兼容格式：gotoStudyResource("ID", "1") 或 gotoStudyResource('ID', '1')
                # 同时也匹配源码中常见的 \t \n 等干扰字符
                pattern = r"gotoStudyResource\s*\(\s*['\"]([A-F0-9a-f]{32})['\"]\s*,\s*['\"]1['\"]\s*\)"
                found_ids = re.findall(pattern, html_content)
                
                # 如果没找到，尝试更宽松的匹配（只找 32 位十六进制 ID）
                if not found_ids:
                    found_ids = re.findall(r"gotoStudyResource\(['\"]([A-F0-9a-f]{32})['\"]", html_content)

                new_found = 0
                for leid in found_ids:
                    if leid not in all_unique_ids:
                        all_unique_ids.append(leid)
                        new_found += 1
                
                self.log(f"    - 本页发现 {new_found} 门新课程")
                
                if current_page >= total_pages:
                    break
                current_page += 1
                time.sleep(1)
                
            except Exception as e:
                self.log(f"[!] 错误: {str(e)}")
                break

        if not all_unique_ids:
            self.log("[!] 未找到有效课程 ID。请确认你粘贴的是“学习路径”的链接。")
            return

        self.log(f"\n[+] 累计获取 {len(all_unique_ids)} 门课程，开始自动化处理...")
        for index, leid in enumerate(all_unique_ids):
            self.run_single_course(leid, f"MOOC课程-{index+1}")
        self.log("\n[完成] 所有 MOOC 任务已处理完毕！")

    # ---------- 专题模式（原有） ----------
    def start_special_topic(self, task_id):
        self.log(f"[*] 模式：专题刷课 | ID: {task_id}")
        ref = f"{self.base_url}/ZttjControl?flag=zttj_earth&categroyID={task_id}"
        payload = {'pageNo': '1', 'pageSize': '1000', 'discussID': task_id, 'pptrainID': task_id}
        res = self.session.post(f"{self.base_url}/ZttjControl?flag=zttj_Lessons", 
                               data=payload, headers={**self.headers, 'Referer': ref}, timeout=30)
        try:
            data = res.json()
            lessons = [(item.get('ID'), item.get('LE_NAME', '专题课程')) for item in data.get('onlineLesson', []) if item.get('ID')]
            for leid, name in lessons: 
                self.run_single_course(leid, name)
            self.log("\n[完成] 专题刷课结束")
        except: 
            self.log("[!] 解析专题 JSON 失败")

    # ---------- 培训班模式（原有，精细版） ----------
    def start_college_train(self, input_url):
        tc_match = re.search(r'tcID=([a-f0-9]+)', input_url)
        if not tc_match:
            self.log("[!] 无法从 URL 提取 tcID")
            return
        tc_id = tc_match.group(1)
        self.log(f"[*] 模式：培训班刷课 | tcID: {tc_id}")

        all_unique_ids = []
        page = 1
        # 初始 Referer 设置为详情页
        current_referer = f"http://gwxt.sgcc.com.cn/www/command/CollegeControl?flag=collegeTC&tcID={tc_id}"

        while True:
            self.log(f"[*] 正在拉取第 {page} 页 (基于 LE_ID 精准匹配)...")
            # 严格按照你发现的请求构造链接
            list_url = f"{self.base_url}/CollegeControl?flag=collegeTC&tcID={tc_id}&tab=collTcLesson&type=&worktypeid=&pageNo1={page}&pageSize1=10&comewho=null"
            
            try:
                # 发送请求，带上动态 Referer
                res = self.session.get(list_url, headers={**self.headers, 'Referer': current_referer}, timeout=30)
                
                # 更新下一次请求的 Referer 为当前页（模拟浏览器行为）
                current_referer = list_url
                
                # 精准匹配 JS 里的 LE_ID: "..."
                found_le_ids = re.findall(r'LE_ID:\s*"([A-F0-9a-f]{32})"', res.text)
                
                new_found_this_page = 0
                for leid in found_le_ids:
                    if leid not in all_unique_ids:
                        all_unique_ids.append(leid)
                        new_found_this_page += 1
                
                if new_found_this_page == 0:
                    self.log(f"[*] 第 {page} 页未解析出新课程 ID，拉取完毕。")
                    break
                
                self.log(f"    - 第 {page} 页发现 {new_found_this_page} 门课程 (累计: {len(all_unique_ids)})")
                page += 1
                time.sleep(1)  # 稍微停顿，防止触发反爬

            except Exception as e:
                self.log(f"[!] 请求出错: {str(e)}")
                break

        if not all_unique_ids:
            self.log("[!] 未找到任何 LE_ID，请检查 Cookie 是否过期或链接是否正确。")
            return

        for index, leid in enumerate(all_unique_ids):
            self.run_single_course(leid, f"培训课程-{index+1}")
        
        self.log("\n[完成] 培训班全课程处理完毕！")

# ================= GUI 界面 =================
class App:
    def __init__(self, root):
        root.title("国网学堂 - 暴力刷题 by Disda (含MOOC)")
        root.geometry("700x700")

        header = tk.Frame(root, pady=10)
        header.pack(fill="x", padx=15)
        
        tk.Label(header, text="工号:").pack(side="left")
        self.ent_user = tk.Entry(header, width=12)
        self.ent_user.insert(0, "3031xxxx")
        self.ent_user.pack(side="left", padx=5)

        tk.Label(root, text="Cookie (包含 bkid 和 JSESSIONID2):").pack(anchor="w", padx=15)
        self.txt_cookie = tk.Text(root, height=4, font=("Consolas", 9))
        self.txt_cookie.pack(fill="x", padx=15, pady=5)

        self.nb = ttk.Notebook(root)
        self.nb.pack(fill="both", padx=15, pady=5)

        # ---------- MOOC 模式（新增） ----------
        self.tab_mooc = tk.Frame(self.nb, pady=10)
        self.nb.add(self.tab_mooc, text="  MOOC 模式  ")
        tk.Label(self.tab_mooc, text="粘贴学习路径 URL (包含 topic_study 或 topic_study_area):").pack(anchor="w", padx=10)
        self.ent_mooc = tk.Entry(self.tab_mooc)
        self.ent_mooc.pack(fill="x", padx=10, pady=5)

        # ---------- 专题模式 ----------
        self.tab_spec = tk.Frame(self.nb, pady=10)
        self.nb.add(self.tab_spec, text="  专题模式  【找到zttj_Lessons开头的header，找discussID】")
        tk.Label(self.tab_spec, text="任务 ID (discussID): ").pack(anchor="w", padx=10)
        self.ent_task = tk.Entry(self.tab_spec)
        self.ent_task.insert(0, "8a84a2fa99eaee6f019a397bb63b6d22")
        self.ent_task.pack(fill="x", padx=10, pady=5)

        # ---------- 培训班模式 ----------
        self.tab_coll = tk.Frame(self.nb, pady=10)
        self.nb.add(self.tab_coll, text="  培训班模式  ")
        tk.Label(self.tab_coll, text="粘贴任意培训班页面 URL:").pack(anchor="w", padx=10)
        self.ent_url = tk.Entry(self.tab_coll)
        self.ent_url.pack(fill="x", padx=10, pady=5)

        self.btn = tk.Button(root, text="🚀 启动脚本", bg="#2c3e50", fg="white", 
                            font=("微软雅黑", 10, "bold"), pady=10, command=self.run)
        self.btn.pack(fill="x", padx=15, pady=10)

        self.log_box = scrolledtext.ScrolledText(root, height=18, bg="#fdfdfd")
        self.log_box.pack(fill="both", padx=15, pady=5, expand=True)

    def run(self):
        user = self.ent_user.get().strip()
        cookie = self.txt_cookie.get("1.0", tk.END).strip()
        mode = self.nb.index(self.nb.select())  # 0: MOOC, 1: 专题, 2: 培训班

        if len(cookie) < 20:
            messagebox.showwarning("提示", "请先填入有效的 Cookie！")
            return

        self.btn.config(state=tk.DISABLED, text="处理中...")
        self.log_box.delete("1.0", tk.END)

        def worker():
            try:
                sub = AccurateIdSubmitter(user, cookie, self.log_box)
                if mode == 0:
                    sub.start_mooc_train(self.ent_mooc.get().strip())
                elif mode == 1:
                    sub.start_special_topic(self.ent_task.get().strip())
                elif mode == 2:
                    sub.start_college_train(self.ent_url.get().strip())
            except Exception as e:
                self.log_box.insert(tk.END, f"\n[Error] {str(e)}\n")
            finally:
                self.btn.config(state=tk.NORMAL, text="🚀 启动脚本")

        threading.Thread(target=worker, daemon=True).start()

if __name__ == "__main__":
    root = tk.Tk()
    style = ttk.Style()
    style.configure("TNotebook.Tab", padding=[20, 5])
    app = App(root)
    root.mainloop()