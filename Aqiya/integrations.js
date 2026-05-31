(function () {
  const CONFIG = {
    formspreeFormId: "mqejonjg",
    posthogApiKey: "REPLACE_WITH_POSTHOG_API_KEY",
    posthogApiHost: "https://us.i.posthog.com",
    clarityProjectId: "wzqsbnfufh",
  };

  const isConfigured = (value, placeholder) =>
    value && value !== placeholder && !value.startsWith("REPLACE_WITH_");

  function setupFormspree() {
    const form = document.querySelector(".waitlist-form");
    if (!form) return;

    const datasetFormId = form.dataset.formspreeFormId;
    const formId = isConfigured(datasetFormId, "REPLACE_WITH_FORMSPREE_FORM_ID")
      ? datasetFormId
      : CONFIG.formspreeFormId;
    const status = form.querySelector(".form-status");

    if (isConfigured(formId, "REPLACE_WITH_FORMSPREE_FORM_ID")) {
      form.action = `https://formspree.io/f/${formId}`;
      return;
    }

    form.addEventListener("submit", (event) => {
      event.preventDefault();
      if (status) {
        status.textContent = "FormspreeのフォームIDを設定してください。";
      }
    });
  }

  function setupPostHog() {
    if (!isConfigured(CONFIG.posthogApiKey, "REPLACE_WITH_POSTHOG_API_KEY")) {
      return;
    }

    /* eslint-disable */
    !(function (t, e) {
      var o, n, p, r;
      e.__SV ||
        ((window.posthog = e),
        (e._i = []),
        (e.init = function (i, s, a) {
          function g(t, e) {
            var o = e.split(".");
            2 == o.length && ((t = t[o[0]]), (e = o[1])),
              (t[e] = function () {
                t.push([e].concat(Array.prototype.slice.call(arguments, 0)));
              });
          }
          ((p = t.createElement("script")).type = "text/javascript"),
            (p.crossOrigin = "anonymous"),
            (p.async = !0),
            (p.src = s.api_host.replace(".i.posthog.com", "-assets.i.posthog.com") + "/static/array.js"),
            (r = t.getElementsByTagName("script")[0]).parentNode.insertBefore(p, r);
          var u = e;
          for (
            void 0 !== a ? (u = e[a] = []) : (a = "posthog"),
              u.people = u.people || [],
              u.toString = function (t) {
                var e = "posthog";
                return "posthog" !== a && (e += "." + a), t || (e += " (stub)"), e;
              },
              u.people.toString = function () {
                return u.toString(1) + ".people (stub)";
              },
              o =
                "init capture register register_once register_for_session unregister unregister_for_session getFeatureFlag getFeatureFlagPayload isFeatureEnabled reloadFeatureFlags updateEarlyAccessFeatureEnrollment getEarlyAccessFeatures on onFeatureFlags onSessionId getSurveys getActiveMatchingSurveys renderSurvey canRenderSurvey canRenderSurveyAsync identify setPersonProperties group resetGroups setPersonPropertiesForFlags resetPersonPropertiesForFlags setGroupPropertiesForFlags resetGroupPropertiesForFlags reset get_distinct_id getGroups get_session_id get_session_replay_url alias set_config startSessionRecording stopSessionRecording sessionRecordingStarted loadToolbar get_property getSessionProperty createPersonProfile opt_in_capturing opt_out_capturing has_opted_in_capturing has_opted_out_capturing clear_opt_in_out_capturing debug".split(
                  " "
                ),
              n = 0;
            n < o.length;
            n++
          )
            g(u, o[n]);
          e._i.push([i, s, a]);
        }),
        (e.__SV = 1));
    })(document, window.posthog || []);
    /* eslint-enable */

    window.posthog.init(CONFIG.posthogApiKey, {
      api_host: CONFIG.posthogApiHost,
      person_profiles: "identified_only",
      capture_pageview: true,
    });
  }

  function setupClarity() {
    if (!isConfigured(CONFIG.clarityProjectId, "REPLACE_WITH_CLARITY_PROJECT_ID")) {
      return;
    }

    (function (c, l, a, r, i, t, y) {
      c[a] =
        c[a] ||
        function () {
          (c[a].q = c[a].q || []).push(arguments);
        };
      t = l.createElement(r);
      t.async = 1;
      t.src = "https://www.clarity.ms/tag/" + i;
      y = l.getElementsByTagName(r)[0];
      y.parentNode.insertBefore(t, y);
    })(window, document, "clarity", "script", CONFIG.clarityProjectId);
  }

  function setupLeadTracking() {
    const form = document.querySelector(".waitlist-form");
    if (!form) return;

    form.addEventListener("submit", () => {
      if (!form.action.startsWith("https://formspree.io/f/")) {
        return;
      }

      if (window.posthog && typeof window.posthog.capture === "function") {
        window.posthog.capture("waitlist_form_submitted", {
          source: "diagnosis_section",
        });
      }

      if (typeof window.clarity === "function") {
        window.clarity("event", "waitlist_form_submitted");
      }
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    setupFormspree();
    setupPostHog();
    setupClarity();
    setupLeadTracking();
  });
})();
