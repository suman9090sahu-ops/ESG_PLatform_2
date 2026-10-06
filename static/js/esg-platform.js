/**
 * MEIL ESG CONTROL TOWER - Vanilla JavaScript Platform Utilities
 * Production-grade client interactivity without heavyweight frontend frameworks.
 */

(function () {
  "use strict";

  // Global namespace for ESG platform utilities
  window.MEIL_ESG = window.MEIL_ESG || {};

  /**
   * File Upload Feedback Handler
   * Displays selected file name and human-readable file size.
   */
  window.handleEsgFileChange = function (input, feedbackId) {
    const feedbackEl = document.getElementById(feedbackId);
    if (!feedbackEl) return;

    if (input.files && input.files.length > 0) {
      const file = input.files[0];
      const nameEl = feedbackEl.querySelector(".file-name");
      const sizeEl = feedbackEl.querySelector(".file-size");

      if (nameEl) nameEl.textContent = file.name;
      if (sizeEl) {
        const kb = (file.size / 1024).toFixed(1);
        const mb = (file.size / (1024 * 1024)).toFixed(2);
        sizeEl.textContent = file.size > 1024 * 1024 ? `${mb} MB` : `${kb} KB`;
      }
      feedbackEl.classList.remove("d-none");
    } else {
      feedbackEl.classList.add("d-none");
    }
  };

  /**
   * Confirmation Dialog Trigger Helper
   * Allows any button with data-esg-confirm-* attributes to populate and show the confirmation modal.
   */
  window.MEIL_ESG.openConfirmation = function (options) {
    const modalId = options.modalId || "esgConfirmationModal";
    const modalEl = document.getElementById(modalId);
    if (!modalEl) return;

    const titleEl = modalEl.querySelector(".modal-title");
    const bodyEl = modalEl.querySelector(".modal-body-text");
    const confirmBtn = modalEl.querySelector(".btn-confirm-action");
    const formEl = modalEl.querySelector("form");

    if (titleEl && options.title) titleEl.textContent = options.title;
    if (bodyEl && options.message) bodyEl.textContent = options.message;
    if (confirmBtn && options.confirmText) confirmBtn.textContent = options.confirmText;
    if (confirmBtn && options.confirmVariant) {
      confirmBtn.className = "btn " + options.confirmVariant + " btn-confirm-action";
    }

    if (formEl && options.actionUrl) {
      formEl.action = options.actionUrl;
    }

    if (typeof bootstrap !== "undefined" && bootstrap.Modal) {
      const modalInstance = bootstrap.Modal.getInstance(modalEl) || new bootstrap.Modal(modalEl);
      modalInstance.show();
    }
  };

  /**
   * Mobile Sidebar Drawer Toggle
   */
  window.MEIL_ESG.toggleSidebar = function () {
    const sidebar = document.getElementById("sidebar");
    const overlay = document.getElementById("sidebarOverlay");
    if (!sidebar) return;

    sidebar.classList.toggle("active");
    if (overlay) {
      overlay.classList.toggle("active");
    }
  };

  /**
   * Close Mobile Sidebar Drawer
   */
  window.MEIL_ESG.closeSidebar = function () {
    const sidebar = document.getElementById("sidebar");
    const overlay = document.getElementById("sidebarOverlay");
    if (sidebar) sidebar.classList.remove("active");
    if (overlay) overlay.classList.remove("active");
  };

  document.addEventListener("DOMContentLoaded", function () {
    // 1. Drag & Drop File Upload Zones
    const dropzones = document.querySelectorAll(".esg-file-dropzone");
    dropzones.forEach(function (zone) {
      ["dragenter", "dragover"].forEach(function (eventName) {
        zone.addEventListener(eventName, function (e) {
          e.preventDefault();
          e.stopPropagation();
          zone.classList.add("dragover");
        }, false);
      });

      ["dragleave", "drop"].forEach(function (eventName) {
        zone.addEventListener(eventName, function (e) {
          e.preventDefault();
          e.stopPropagation();
          zone.classList.remove("dragover");
        }, false);
      });

      zone.addEventListener("drop", function (e) {
        const dt = e.dataTransfer;
        const files = dt.files;
        const fileInput = zone.querySelector('input[type="file"]');
        if (fileInput && files.length) {
          fileInput.files = files;
          const feedbackId = fileInput.id + "_feedback";
          window.handleEsgFileChange(fileInput, feedbackId);
        }
      }, false);
    });

    // 2. Setup Data-Attribute Confirmation Triggers
    document.addEventListener("click", function (e) {
      const trigger = e.target.closest("[data-esg-confirm]");
      if (!trigger) return;

      e.preventDefault();
      window.MEIL_ESG.openConfirmation({
        modalId: trigger.getAttribute("data-esg-modal-id") || "esgConfirmationModal",
        title: trigger.getAttribute("data-esg-confirm-title") || "Confirm Action",
        message: trigger.getAttribute("data-esg-confirm-message") || "Are you sure you wish to proceed?",
        confirmText: trigger.getAttribute("data-esg-confirm-btn") || "Confirm",
        confirmVariant: trigger.getAttribute("data-esg-confirm-variant") || "btn-danger",
        actionUrl: trigger.getAttribute("data-esg-confirm-url") || "#"
      });
    });

    // 3. Mobile Sidebar Toggle Button
    const mobileToggleBtn = document.querySelector('[data-toggle="offcanvas"]');
    if (mobileToggleBtn) {
      mobileToggleBtn.addEventListener("click", function (e) {
        e.preventDefault();
        window.MEIL_ESG.toggleSidebar();
      });
    }

    const overlay = document.getElementById("sidebarOverlay");
    if (overlay) {
      overlay.addEventListener("click", function () {
        window.MEIL_ESG.closeSidebar();
      });
    }

    // 4. Keyboard Accessibility: Escape key closes modal & mobile drawer
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") {
        window.MEIL_ESG.closeSidebar();
      }
    });

    // 5. Initialize Bootstrap 5 Tooltips & Popovers
    if (typeof bootstrap !== "undefined") {
      if (bootstrap.Tooltip) {
        const tooltipElements = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
        tooltipElements.forEach(function (el) {
          new bootstrap.Tooltip(el);
        });
      }
      if (bootstrap.Popover) {
        const popoverElements = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
        popoverElements.forEach(function (el) {
          new bootstrap.Popover(el);
        });
      }
    }
  });
})();
