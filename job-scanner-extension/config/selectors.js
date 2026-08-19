(() => {
  const ns = (globalThis.BossPlugin ??= {});

  // 截图不能提供真实 DOM；候选项按“较稳定语义 -> 宽松结构”排序。
  // 用户应通过调试 API 验证后，把真实 selector 放到各数组最前面。
  ns.SELECTORS = Object.freeze({
    jobList: [
      ".job-list-box",
      ".job-list-container",
      ".job-list",
      "[class*='job-list']"
    ],
    jobCard: [
      "li.job-card-wrapper",
      ".job-card-wrapper",
      ".job-card-box",
      "[data-jobid]",
      "[data-job-id]"
    ],
    cardLink: ["a[href*='/job_detail/']", "a[href*='jobId=']"],
    cardTitle: [".job-name", ".job-title", "[class*='job-name']"],
    cardSalary: [".salary", ".job-salary", "[class*='salary']"],
    cardLocation: [".job-area", ".job-location", ".text-city", "[class*='job-area']"],
    cardCompany: [
      ".company-info .company-name",
      ".job-card-footer .company-name",
      ".company-name",
      "[class*='company-name']",
      ".boss-name"
    ],
    cardMeta: [
      ".job-info .tag-list li",
      ".job-card-footer .tag-list li",
      ".job-card-wrapper .tag-list li",
      ".job-card-box .tag-list li",
      "[class*='tag-list'] li"
    ],
    detailRoot: [
      ".job-detail-box",
      ".job-detail-container",
      ".job-detail",
      "[class*='job-detail']"
    ],
    jobTitle: [
      ".job-detail-header .job-name",
      ".job-detail-box .job-name",
      ".job-name",
      "h1"
    ],
    salary: [".job-detail-header .salary", ".job-detail-box .salary", ".job-info .salary", ".salary"],
    location: [".job-detail-header .text-city", ".job-info .text-city", ".job-area", ".job-location", "[class*='location']"],
    experience: [".job-detail-header .text-experiece", ".job-info .text-experiece", ".text-experience", ".job-experience", "[class*='experience']"],
    education: [".job-detail-header .text-degree", ".job-info .text-degree", ".text-degree", ".job-degree", "[class*='degree']"],
    detailMeta: [
      ".job-info .text-desc",
      ".job-detail-header .text-desc",
      ".job-primary .info-primary p span"
    ],
    companyName: [
      ".job-detail-box .company-name",
      ".company-info .company-name",
      ".company-info .name",
      ".company-info h3",
      "[class*='company-name']"
    ],
    hrName: [".boss-info .name", ".boss-info-attr .name", ".boss-name", "[class*='boss-name']"],
    hrTitle: [".boss-info .boss-position", ".boss-info-attr .boss-position", ".boss-position", "[class*='boss-position']"],
    jobDescription: [
      ".job-sec-text",
      ".job-detail-section .text",
      ".job-description",
      "[class*='job-description']"
    ],
    jobTags: [
      ".job-tags span",
      ".job-keyword-list li",
      ".job-detail-box [class*='tag'] span"
    ],
    communicateButton: [
      "button.btn-startchat",
      "a.btn-startchat",
      "[data-action='start-chat']",
      "button[class*='startchat']"
    ],
    successModal: [
      "[role='dialog']",
      "[aria-modal='true']",
      ".dialog-wrap",
      ".dialog-container",
      ".boss-dialog",
      "[class*='dialog-container']",
      "[class*='modal-container']",
      "[class*='modal']"
    ],
    stayHereButton: [
      "button.btn-outline",
      "a.btn-outline",
      "button[class*='cancel']",
      "button[class*='secondary']",
      "[data-action='stay']",
      "[class*='dialog-footer'] button",
      "[class*='modal-footer'] button"
    ],
    closeModalButton: [
      "button[aria-label*='关闭']",
      "[role='button'][aria-label*='关闭']",
      "button[title*='关闭']",
      "[role='button'][title*='关闭']",
      ".dialog-close",
      "[class*='dialog-close']",
      "[class*='modal-close']",
      "[class*='close-icon']",
      "[class*='icon-close']"
    ]
  });
})();
