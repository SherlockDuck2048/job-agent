# scan_strategies.py - 用户提供的验证过真实 URL
# 生成时间: 2026-04-10
# 来源: CCO 提供的 67 个公司招聘链接（已验证）

SCAN_STRATEGIES = {

    # ==================== 综合招聘平台（5个）====================
    "linkedin": {
        "name": "LinkedIn",
        "method": "cdp_input",
        "url": "https://www.linkedin.com/jobs/search/?keywords=AI&location=Hong%20Kong",
        "actions": [
            {"type": "fill", "selector": "input[aria-label*='Search']", "value": "{keyword}"},
            {"type": "click", "selector": "button[aria-label*='Search']"},
            {"type": "wait", "ms": 5000}
        ],
        "selectors": {
            "job_card": ".job-card-container",
            "title": ".job-card-list__title--link",
            "company": ".job-card-container__company-name"
        },
        "notes": "M1: CDP + 登录态，需Chrome已登录"
    },
    "indeed": {
        "name": "Indeed",
        "method": "cdp_url",
        "url": "https://hk.indeed.com/jobs?q=AI&l=Hong+Kong",
        "selectors": {
            "job_card": ".job_seen_beacon",
            "title": "h2.jobTitle",
            "company": ".companyName",
            "location": ".companyLocation"
        },
        "notes": "M3: URL参数翻页，cf-turnstile参数需手动处理"
    },
    "jobsdb": {
        "name": "JobsDB",
        "method": "skip",
        "reason": "Cloudflare反爬，无法绕过"
    },
    "michaelpage": {
        "name": "Michael Page",
        "method": "skip",
        "reason": "需登录注册才能查看职位列表"
    },
    "hays": {
        "name": "Hays",
        "method": "cdp_url",
        "url": "https://www.hays.com.hk/job-search/ai-jobs-in-hong-kong-hong-kong?q=Ai&location=Hong%20kong,%20Hong%20kong&sortType=0",
        "selectors": {
            "job_card": "a[href*='job-detail']",
            "title": ".job-title",
            "company": ".job-company"
        },
        "notes": "sortType=0 (最新), scroll=8次"
    },

    # ==================== 猎头网站（7个）====================
    "robertwalters": {
        "name": "Robert Walters",
        "method": "skip",
        "reason": "PerimeterX反爬严，跳过"
    },
    "adecco": {
        "name": "Adecco",
        "method": "cdp_url",
        "url": "https://www.adecco.com/en-hk?jobTitle=AI&jobLocation=Hong+Kong&radius=100",
        "selectors": {
            "job_card": ".job-result",
            "title": ".job-title"
        }
    },
    "persol": {
        "name": "PERSOL Hong Kong",
        "method": "cdp_url",
        "url": "https://jobs.persolhongkong.com/?utm_source=internal_navigation&utm_medium=persolhongkong_site&utm_campaign=country_site_to_job_portal&utm_content=job_seekers_page_fv_search_jobs&page=1&search=AI",
        "selectors": {
            "job_card": ".job-result",
            "title": ".job-title"
        }
    },
    "captar": {
        "name": "Captar Partners",
        "method": "cdp_url",
        "url": "https://www.captarpartners.com/jobs?sort_type=relevance&query=AI&radius_location=&radius=8km&submit=Search",
        "selectors": {
            "job_card": ".job-listing",
            "title": "h3"
        }
    },
    "connectedgroup": {
        "name": "ConnectedGroup",
        "method": "cdp_url",
        "url": "https://www.connectedgroup.com/job-results?keyword=AI#/hong-kong",
        "selectors": {
            "job_card": ".job-result",
            "title": "h4"
        }
    },
    "randstad": {
        "name": "Randstad",
        "method": "cdp_url",
        "url": "https://www.randstad.com.hk/jobs/q-ai/",
        "selectors": {
            "job_card": ".job-card",
            "title": ".job-title"
        },
        "notes": "React SPA，/jobs/?q=格式"
    },
    "seamatch": {
        "name": "Seamatch",
        "method": "cdp_url",
        "url": "https://www.seamatch.com/job-seekers/hot-jobs?filter%5Bsearch%5D=AI&filter%5Blocation%5D=#content",
        "selectors": {
            "job_card": ".job-result",
            "title": ".job-title"
        }
    },
    "ambition": {
        "name": "Ambition",
        "method": "cdp_url",
        "url": "https://www.ambition.com.hk/jobs?sort_type=relevance&query=AI&selected_locations=1819729&submit=Search",
        "selectors": {
            "job_card": ".job-result",
            "title": ".job-title"
        }
    },

    # ==================== 银行/金融（5个）====================
    "bochk": {
        "name": "BOCHK",
        "method": "cdp_url",
        "url": "https://careers.pageuppeople.com/798/cw/en/search/?search-keyword=AI",
        "selectors": {
            "job_card": "a[href*='/job/']",
            "title": "a[href*='/job/']"
        },
        "notes": "PageUp People CMS; 15 jobs single-page; href=/job/{id}/{slug}"
    },
    "hsbc": {
        "name": "HSBC",
        "method": "cdp_url",
        "url": "https://portal.careers.hsbc.com/careers?query=AI&location=Hong%20Kong&pid=563774610187996&domain=hsbc.com&sort_by=relevance&triggerGoButton=false",
        "selectors": {
            "job_card": ".job-card",
            "title": ".job-title"
        },
        "notes": "portal.careers.hsbc.com (非 mycareer.hsbc.com)"
    },
    "icbcasia": {
        "name": "ICBC Asia",
        "method": "skip",
        "reason": "无公开搜索页，需手动浏览 https://www.icbcasia.com/hk/en/about-us/career-opportunities/professional-hires.html"
    },
    "ccbasia": {
        "name": "CCB Asia",
        "method": "skip",
        "reason": "无公开搜索页，需手动 https://online.asia.ccb.com/PersonalHKWeb/careeropportunity/webForm/actShowList.do"
    },
    "ccb": {
        "name": "CCB Asia",
        "url": "https://online.asia.ccb.com/PersonalHKWeb/careeropportunity/webForm/actShowList.do",
        "method": "urllist"
    },
    "dahsing": {
        "name": "大新银行",
        "method": "cdp_url",
        "url": "https://phg.tbe.taleo.net/phg03/ats/careers/v2/searchResults?org=DSB&cws=45&act=sort&sortColumn=1&sortOrder=D",
        "selectors": {
            "job_card": ".search-result",
            "title": ".job-title"
        }
    },

    # ==================== 咨询/四大（5个）====================
    "accenture": {
        "name": "Accenture",
        "method": "cdp_url",
        "url": "https://www.accenture.com/hk-en/careers/jobsearch?jk=AI&sb=0&vw=0&is_rj=0&pg=1",
        "selectors": {
            "job_card": ".job-card",
            "title": ".job-title"
        }
    },
    "deloitte": {
        "name": "Deloitte",
        "method": "playwright_dom",
        "url": "https://ehjobs.deloitte.com.cn/SU649e304a6a9f0ef690533e9a/pb/social.html?workPlaceCode=0%2F4%2F595%2F538135297",
        "pagination": "currentPage=N",
        "notes": "ehjobs平台，DOM body文本解析，翻页URL参数 currentPage=N"
    },
    "ey": {
        "name": "EY",
        "method": "cdp_url",
        "url": "https://app.mokahr.com/social-recruitment/ey/47410#/jobs?keyword=AI&location%5B0%5D=Hongkong&page=1&anchorName=jobsList",
        "selectors": {
            "job_card": ".job-card",
            "title": ".job-title"
        }
    },
    "pwc": {
        "name": "PwC",
        "method": "cdp_url",
        "url": "https://www.pwccn.com/en/careers/experienced-jobs.html",
        "note": "搜索过滤AI=72jobs/8pages，table tr行提取，JS click()翻页，完整URL去重，launch独立浏览器"
    },
    "kpmg": {
        "name": "KPMG",
        "method": "cdp_url",
        "url": "https://app.mokahr.com/social-recruitment/kpmg/74216#/jobs?keyword=AI&location%5B0%5D=Hongkong&page=1&anchorName=jobsList",
        "selectors": {
            "job_card": ".job-card",
            "title": ".job-title"
        }
    },

    # ==================== 外资金融（7个）====================
    "citi": {
        "name": "Citi",
        "method": "cdp_url",
        "url": "https://jobs.citi.com/search-jobs/AI/Hong%20Kong%20SAR/287/1/2/1819730/22x25/114x16667175292969/50/2",
        "selectors": {
            "job_card": "[data-job-id]",
            "title": ".job-title"
        },
        "notes": "Taleo系统，页面加载后有30个data-job-id元素"
    },
    "jpmorgan": {
        "name": "JPMorgan Chase",
        "method": "cdp_url",
        "url": "https://jpmc.fa.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1001/jobs?keyword=AI&location=Hong+Kong&locationId=300000000289330&locationLevel=country&mode=location",
        "selectors": {
            "job_card": "div.job-tile",
            "title": ".job-tile__title"
        },
        "notes": "Oracle HCM系统"
    },
    "sc": {
        "name": "Standard Chartered",
        "method": "cdp_url",
        "url": "https://jobs.standardchartered.com/search/?q=AI&locationsearch=&skillsSearch=false&markerViewed=&carouselIndex=&facetFilters=%7B%22jobLocationCity%22%3A%5B%22Central%22%2C%22Kwun+Tong%22%5D%7D&pageNumber=0",
        "selectors": {
            "job_card": ".job-result",
            "title": ".job-title"
        }
    },
    "ubs": {
        "name": "UBS",
        "method": "cdp_url",
        "url": "https://jobs.ubs.com/TGnewUI/Search/home/HomeWithPreLoad?partnerid=25008&siteid=5012&PageType=searchResults&SearchType=linkquery&LinkID=15231#keyWordSearch=AI&locationSearch=",
        "selectors": {
            "job_card": ".job-result",
            "title": ".job-title"
        },
        "notes": "TGnewUI SPA; keyword via JS hash; li.job cards; location=first .position3; 51 jobs no pagination"
    },
    "dbs": {
        "name": "DBS",
        "method": "cdp_url",
        "url": "https://dbs.wd3.myworkdayjobs.com/zh-CN/DBS_Careers?q=AI&locationCountry=d4afdeb461d446e4babd204bd102dba8",
        "selectors": {
            "job_card": "a[href*='/job/']",
            "title": "[data-automation-id='positionTitle']",
            "location": "[data-automation-id='secondaryLocation']",
            "next_button": "button[aria-label*='next']"
        },
        "notes": "Workday SPA; keyword=q=AI; locationCountry过滤香港; pagination via aria-label next button"
    },
    "goldman": {
        "name": "Goldman Sachs",
        "method": "cdp_url",
        "url": "https://higher.gs.com/results?LOCATION=Hong%20Kong&page=1&search=AI&sort=RELEVANCE",
        "selectors": {
            "job_card": ".job-card",
            "title": ".job-title"
        }
    },
    "macquarie": {
        "name": "Macquarie",
        "method": "cdp_url",
        "url": "https://recruitment.macquarie.com/en_US/careers/SearchJobs/AI?10671=%5B871432%5D&10671_format=21337&listFilterMode=1&jobRecordsPerPage=9&",
        "selectors": {
            "job_card": ".job-result",
            "title": ".job-title"
        }
    },

    # ==================== 保险（6个）====================
    "aia": {
        "name": "AIA",
        "method": "cdp_url",
        "base_url": "https://aia.wd3.myworkdayjobs.com/zh-TW/External?q=AI&keyword=AI&locationCountry=d4afdeb461d446e4babd204bd102dba8",
        "system": "Workday",
        "selectors": {
            "job_link": "a[href*='/job/']"
        },
        "notes": "Workday SPA，使用q=参数，页面动态加载"
    },
    "manulife": {
        "name": "Manulife",
        "method": "cdp_url",
        "base_url": "https://manulife.wd3.myworkdayjobs.com/en-US/MFCJH_Jobs?q=AI&keyword=AI&Location_Country=d4afdeb461d446e4babd204bd102dba8",
        "system": "Workday",
        "selectors": {
            "job_link": "a[href*='/job/']"
        }
    },
    "prudential": {
        "name": "Prudential",
        "method": "cdp_url",
        "base_url": "https://prudential.wd3.myworkdayjobs.com/en-US/prudential?q=AI&keyword=AI&locationHierarchy1=d4afdeb461d446e4babd204bd102dba8",
        "system": "Workday",
        "selectors": {
            "job_link": "a[href*='/job/']"
        }
    },
    "zurich": {
        "name": "Zurich Insurance",
        "method": "cdp_url",
        "url": "https://www.careers.zurich.com/search/?createNewAlert=false&q=AI&locationsearch=hong+kong&optionsFacetsDD_shifttype=&optionsFacetsDD_department=&optionsFacetsDD_customfield3=",
        "selectors": {
            "job_card": ".job-result",
            "title": ".job-title"
        }
    },
    "sunlife": {
        "name": "Sun Life",
        "method": "cdp_url",
        "base_url": "https://sunlife.wd3.myworkdayjobs.com/en-US/Experienced-Jobs?q=AI&keyword=AI&Location_Country=d4afdeb461d446e4babd204bd102dba8",
        "system": "Workday",
        "selectors": {
            "job_link": "a[href*='/job/']"
        }
    },
    "aig": {
        "name": "AIG",
        "method": "cdp_url",
        "base_url": "https://aig.wd1.myworkdayjobs.com/zh-CN/aig?q=AI&keyword=AI&locationCountry=6cb77610a8a543aea2d6bc10457e35d4&locationCountry=d4afdeb461d446e4babd204bd102dba8",
        "system": "Workday",
        "selectors": {
            "job_link": "a[href*='/job/']"
        }
    },

    # ==================== 科技（4个）====================
    "ibm": {
        "name": "IBM",
        "method": "cdp_url",
        "url": "https://www.ibm.com/careers/search?field_keyword_05[0]=Hong%20Kong&q=AI",
        "selectors": {
            "job_card": ".bx--result-item",
            "title": ".bx--job-title"
        }
    },
    "microsoft": {
        "name": "Microsoft",
        "method": "cdp_url",
        "url": "https://apply.careers.microsoft.com/careers?query=AI&start=0&location=HONG+KONG&pid=1970393556650081&sort_by=relevance&filter_include_remote=1",
        "selectors": {
            "job_card": ".job-card",
            "title": ".job-title"
        }
    },
    "pccw": {
        "name": "PCCW",
        "method": "cdp_url",
        "url": "https://job.pccw.com/search?q=AI",
        "selectors": {
            "job_card": ".job-result",
            "title": ".job-title"
        }
    },
    "hkt": {
        "name": "HKT",
        "method": "cdp_url",
        "url": "https://job.pccw.com/hkt/search/?createNewAlert=false&q=AI&optionsFacetsDD_country=&optionsFacetsDD_city=&optionsFacetsDD_customfield1=&optionsFacetsDD_shifttype=",
        "selectors": {
            "job_card": ".job-result",
            "title": ".job-title"
        }
    },

    # ==================== 香港机构（11个）====================
    "hkex": {
        "name": "HKEX",
        "method": "cdp_url",
        "base_url": "https://hkex.wd3.myworkdayjobs.com/zh-CN/HKEXCareerPage?q=AI&keyword=AI",
        "system": "Workday",
        "selectors": {
            "job_link": "a[href*='/job/']"
        }
    },
    "hkjc": {
        "name": "HKJC",
        "method": "cdp_url",
        "url": "https://careers.hkjc.com/search/?createNewAlert=false&q=AI&locationsearch=hong+kong&optionsFacetsDD_facility=&optionsFacetsDD_location=&optionsFacetsDD_shifttype=",
        "selectors": {
            "job_card": ".search-result",
            "title": ".job-title"
        }
    },
    "hkairport": {
        "name": "香港机场管理局",
        "method": "cdp_url",
        "url": "https://careers.hkairport.com/careersection/ex/jobsearch.ftl",
        "selectors": {
            "job_card": ".search-result",
            "title": ".job-title"
        }
    },
    "clp": {
        "name": "CLP 中电",
        "method": "cdp_url",
        "url": "https://iabhtj.fa.ocs.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CLP-Recruitment-System/jobs?keyword=AI&mode=job-location",
        "selectors": {
            "job_card": ".job-tile",
            "title": ".job-tile__title"
        }
    },
    "cathay": {
        "name": "Cathay Pacific",
        "method": "cdp_url",
        "url": "https://careers.cathaypacific.com/cn/careers/jobs?keyword=AI&sortby=relevance&page=1&locations=hong-kong",
        "selectors": {
            "job_card": ".search-result",
            "title": ".job-title"
        }
    },
    "hkelectric": {
        "name": "港灯",
        "method": "skip",
        "reason": "无公开搜索页，需手动 https://www.hkelectric.com/en/our-people/job-opportunities"
    },
    "shkp": {
        "name": "新鸿基地产",
        "method": "skip",
        "reason": "无公开搜索页，需手动 https://www.shkp.com/zh-HK/work-with-us/job-vacancies?jobtitle=AI"
    },
    "swire": {
        "name": "Swire Properties",
        "method": "cdp_url",
        "url": "https://careers.swireproperties.com/en-hk/jobs?page=1&keyword=AI",
        "selectors": {
            "job_card": ".search-result",
            "title": ".job-title"
        }
    },
    "zabank": {
        "name": "ZA Bank",
        "method": "skip",
        "reason": "无公开搜索页，需手动 https://za.group/join-us"
    },
    "fubonbank": {
        "name": "富邦银行",
        "method": "skip",
        "reason": "无公开搜索页，需手动 https://www.fubonbank.com.hk/en/careers.html"
    },
    "hkist": {
        "name": "港灯/南商NCB",
        "method": "skip",
        "reason": "无公开搜索页，需手动浏览"
    },

    # ==================== 中资/其他（10个）====================
    "ocbc": {
        "name": "OCBC",
        "method": "cdp_url",
        "base_url": "https://ocbc.wd102.myworkdayjobs.com/zh-CN/External?q=AI&Country=d4afdeb461d446e4babd204bd102dba8",
        "system": "Workday",
        "selectors": {
            "job_link": "a[href*='/job/']"
        }
    },
    "cmbi": {
        "name": "招银国际",
        "method": "skip",
        "reason": "无公开搜索页，需手动 https://www.cmbi.com.hk/zh-CN/society"
    },
    "haitong": {
        "name": "海通证券",
        "method": "skip",
        "reason": "海通国际官方URL目前不可用，待之后再试。备选: https://jobs.ctgoodjobs.hk/company/haitong-securities"
    },
    "cicc": {
        "name": "中金CICC",
        "method": "cdp_url",
        "base_url": "https://cicc.zhiye.com/custom/social?&hideMenu=1",
        "system": "Zhiye",
        "pagination": "layui-laypage",
        "total_jobs": 203,
        "total_pages": 21,
        "selectors": {
            "job_row": "tr.tr_dom",
            "job_link": "a[href*='jobAdId=']",
            "title": "a.w280 b",
            "category": "span.cate_name"
        }
    },
    "cncbi": {
        "name": "中信国际",
        "method": "cdp_url",
        "base_url": "https://cncbinternational.wd3.myworkdayjobs.com/zh-CN/CNCBIExternalCareerSite?q=AI",
        "system": "Workday",
        "selectors": {
            "job_link": "a[href*='/job/']"
        }
    },
    "crcapital": {
        "name": "华润香港",
        "method": "cdp_url",
        "url": "https://www.crcapital.com.hk/shzp/index.html",
        "system": "Custom",
        "selectors": {
            "job_card": ".job-card, .job-listing, article, [class*='job']",
            "title": "h1, h2, h3, .job-title, a",
            "link": "a[href]"
        },
        "notes": "扫描结果与网页实际不符（2026-04-17用户反馈），已跳过暂不修复"
    },
    "bea": {
        "name": "BEA 东亚银行",
        "method": "cdp_url",
        "url": "https://careers.hkbea.com/psp/hcmprd/EMPLOYEE/HRMS/c/HRS_HRAM.HRS_APP_SCHJOB.GBL?Page=HRS_APP_SCHJOB&FOCUS=Applicant&FolderPath=PORTAL_ROOT_OBJECT.HC_HRS_CE_GBL2&IsFolder=false&IgnoreParamTempl=FolderPath%252cIsFolder",
        "selectors": {
            "job_card": ".search-result",
            "title": ".job-title"
        }
    },
    "bnp": {
        "name": "BNP Paribas",
        "method": "cdp_url",
        "url": "https://group.bnpparibas/en/careers/all-job-offers/hong-kong/i-am-an-experienced-professional?q=AI",
        "selectors": {
            "job_card": ".job-card",
            "title": ".job-title"
        }
    },
    "mckinsey": {
        "name": "McKinsey",
        "method": "cdp_url",
        "url": "https://www.mckinsey.com/careers/search-jobs?q=AI&cities=Hong+Kong+SAR&query=ai",
        "selectors": {
            "job_card": ".job-card",
            "title": ".job-title"
        }
    },
    "classywheeler": {
        "name": "Classy Wheeler",
        "method": "cdp_url",
        "url": "https://www.classywheeler.com.hk/job/?keyword=AI&industry=0",
        "selectors": {
            "job_card": ".job-result",
            "title": ".job-title"
        }
    },

    "axa": {
        "name": "AXA",
        "method": "cdp_url",
        "url": "https://careers.axa.com/careers-home/jobs?sortBy=relevance&country=Hong%20Kong&keywords=AI",
        "notes": "ICIMS SPA; page=N URL param pagination; stop when 0 jobs; UA required (403 without); job links=/jobs/XXXXX; 11 total jobs HK"
    },

    "fwd": {
        "name": "FWD",
        "method": "cdp_url",
        "base_url": "https://fwd.wd3.myworkdayjobs.com/en-US/FWDcareersite?q=AI&locationCountry=d4afdeb461d446e4babd204bd102dba8",
        "system": "Workday",
        "selectors": {
            "job_link": "a[href*='/job/']"
        },
        "notes": "Workday SPA; button[aria-label*='next'] pagination; href主干去重; Stage1抓链接Stage2抓JD"
    }
}

# ======== 方法统计 ========
METHOD_STATS = {"http": [], "cdp_url": [], "cdp_input": [], "cdp_login": [], "skip": []}
for key, config in SCAN_STRATEGIES.items():
    method = config.get("method", "unknown")
    if method in METHOD_STATS:
        METHOD_STATS[method].append(config["name"])

if __name__ == "__main__":
    print("=== Scan Method Statistics ===\n")
    for method, sites in METHOD_STATS.items():
        print(f"{method.upper()}: {len(sites)} sites")
        for site in sites:
            print(f"  - {site}")
        print()
