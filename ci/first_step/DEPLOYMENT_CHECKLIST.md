# MAHOUN Heavy Lock - Deployment Checklist

## 📋 Pre-Deployment

### 1. Review Configuration
- [ ] Read `CI_LOCK.md` completely
- [ ] Understand all 7 gates
- [ ] Review complexity thresholds in `ci/first_step/complexity_thresholds.json`
- [ ] Check `.github/workflows/ci.yml` settings

### 2. Local Testing
```bash
# Test each gate individually
./ci/first_step/gate_0_integrity.sh
./ci/first_step/gate_1_lint.sh
./ci/first_step/gate_2_types.sh
./ci/first_step/gate_3_reality.sh
./ci/first_step/gate_4_antimock.sh
./ci/first_step/gate_5_determinism.sh
./ci/first_step/gate_6_artifacts.sh

# Test full pipeline
./scripts/ci_run_first_step.sh
```

### 3. Fix Existing Issues
- [ ] Fix all placeholder `pass` statements detected by Gate 0
- [ ] Remove `TODO`/`FIXME` from core code
- [ ] Fix linting issues detected by Gate 1
- [ ] Resolve type errors detected by Gate 2
- [ ] Ensure all tests pass (Gate 3)
- [ ] Verify modules meet complexity thresholds (Gate 4)
- [ ] Confirm tests are deterministic (Gate 5)

---

## 🚀 Deployment Steps

### Step 1: Install Pre-commit Hooks
```bash
pip install pre-commit
pre-commit install
```

### Step 2: Configure GitHub/GitLab

#### For GitHub:
1. Push `.github/workflows/ci.yml` to repository
2. Go to Settings → Branches → main
3. Enable "Require status checks to pass before merging"
4. Select all gate checks:
   - `gate-0-integrity`
   - `gate-1-lint`
   - `gate-2-types`
   - `gate-3-reality`
   - `gate-4-antimock`
   - `gate-5-determinism`
   - `gate-6-artifacts`
5. Enable "Require branches to be up to date before merging"
6. Enable "Require at least 1 approval"
7. Disable "Allow force pushes" (critical!)

#### For GitLab:
1. Push `.gitlab-ci.yml` to repository
2. Go to Settings → Repository → Protected Branches
3. Protect `main` branch
4. Enable "Allowed to merge: Developers + Maintainers"
5. Enable "Allowed to push: No one"
6. Go to Settings → CI/CD → General pipelines
7. Enable "Only allow merge requests to be merged if the pipeline succeeds"

### Step 3: Test CI Pipeline
1. Create a test branch:
   ```bash
   git checkout -b test/ci-gate-system
   ```

2. Make a trivial change:
   ```bash
   echo "# CI Test" >> README.md
   git add README.md
   git commit -m "test: Verify CI gates"
   git push origin test/ci-gate-system
   ```

3. Create Pull Request

4. Verify all gates run and report status

5. Merge if all pass

### Step 4: Communicate to Team
```markdown
## 🔒 New CI/CD Gates Active

Starting today, all PRs must pass 6 mandatory gates:

1. **Gate 0:** Repo Integrity (no placeholders/secrets)
2. **Gate 1:** Format/Lint (ruff)
3. **Gate 2:** Type Safety (pyright/mypy)
4. **Gate 3:** Phase-1 Reality Tests (137 tests)
5. **Gate 4:** Anti-Mock Proof (real implementations)
6. **Gate 5:** Determinism Proof (consistent results)

### How to run locally:
```bash
make ci-first-step
```

### Documentation:
- Full Guide: `CI_LOCK.md`
- Quick Start: `ci/first_step/README.md`

### Expected time: ~2 minutes

Questions? Ask in #platform-team
```

---

## ✅ Post-Deployment Verification

### Week 1: Monitor Closely
- [ ] Check all PRs pass gates
- [ ] Monitor gate durations (should be <2 min total)
- [ ] Collect feedback from developers
- [ ] Fix any false positives

### Week 2-4: Tune
- [ ] Review which gates fail most often
- [ ] Adjust complexity thresholds if needed
- [ ] Update baseline files
- [ ] Document common issues in CI_LOCK.md

### Month 1: Measure
- [ ] Calculate average gate duration
- [ ] Measure PR merge time impact
- [ ] Count bugs prevented
- [ ] Survey developer satisfaction

---

## 🔧 Maintenance Schedule

### Daily
- Monitor CI failures
- Help developers debug gate failures

### Weekly
- Review gate duration trends
- Check for flaky tests (Gate 5 failures)
- Update documentation based on common questions

### Monthly
- Review and update complexity thresholds
- Audit secrets patterns
- Update dependencies (ruff, pytest, etc.)
- Review and prune baseline files

### Quarterly
- Comprehensive gate effectiveness review
- Consider new gates (based on common bugs)
- Retire ineffective gates
- Update this checklist

---

## 🚨 Rollback Plan

If gates cause severe disruption:

### Emergency Rollback (< 1 hour)
1. Disable required status checks in repo settings
2. Announce temporary suspension
3. Investigate root cause
4. Fix and re-enable

### Gradual Rollback (if fundamental issues)
1. Make gates optional (warning only)
2. Fix issues in separate PRs
3. Re-enable gates one by one
4. Monitor each gate independently

---

## 📊 Success Metrics

### Primary KPIs
- **Gate Pass Rate:** Target >95%
- **Average Duration:** Target <2 minutes
- **False Positive Rate:** Target <5%

### Secondary KPIs
- **Bugs Caught:** Track placeholders/secrets prevented
- **Developer Satisfaction:** Survey quarterly
- **Time to Merge:** Should not increase >10%

---

## 🎓 Training Resources

### For Developers
- `CI_LOCK.md` - Complete guide
- `ci/first_step/README.md` - Gate details
- `first_step_ci_cd/README.md` - Test suite docs

### For Maintainers
- `.github/workflows/ci.yml` - CI configuration
- `scripts/ci_run_first_step.sh` - Runner script
- This checklist

---

## 📞 Support

### Issues?
1. Check `CI_LOCK.md` troubleshooting section
2. Run gate locally to reproduce
3. Ask in #ci-cd or #platform-team
4. Tag @platform-maintainers if urgent

### Want to modify gates?
1. Propose changes in RFC
2. Test thoroughly locally
3. Update documentation
4. Get 2+ reviewer approvals
5. Monitor impact after deployment

---

## ✅ Deployment Sign-off

| Item | Status | Date | Signed By |
|------|--------|------|-----------|
| All scripts tested locally | ☐ | | |
| GitHub/GitLab configured | ☐ | | |
| Team notified | ☐ | | |
| Documentation complete | ☐ | | |
| Monitoring setup | ☐ | | |
| Rollback plan tested | ☐ | | |

**Final Approval:** _______________________ Date: _______

---

**Version:** 1.0.0  
**Last Updated:** December 26, 2025  
**Next Review:** January 26, 2026






