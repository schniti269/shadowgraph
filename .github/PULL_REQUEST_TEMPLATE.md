# Pull Request

## Description
Brief summary of what this PR does.

## Type of Change
- [ ] Bug fix (non-breaking change which fixes an issue)
- [ ] New feature (non-breaking change which adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to change)
- [ ] Documentation update
- [ ] Performance improvement
- [ ] Refactoring

## Related Issues
Closes #[issue number]

## How Has This Been Tested?
Describe the tests you ran and how to reproduce:
- [ ] Local testing in Extension Development Host (F5)
- [ ] Python tests: `npm run test:python`
- [ ] TypeScript tests: `npm test` (if applicable)
- [ ] Manual testing in VS Code

### Test Scenario
```
1. Step one
2. Step two
3. Verify result
```

## Screenshots (if applicable)
Add screenshots showing the feature working.

## Checklist
- [ ] My code follows the code style guidelines (ESLint + Ruff)
- [ ] I have performed a self-review of my own code
- [ ] I have commented my code, particularly in hard-to-understand areas
- [ ] I have made corresponding changes to the documentation
- [ ] My changes generate no new warnings or errors
- [ ] I have added tests that prove my fix is effective or that my feature works
- [ ] New and existing unit tests pass locally with my changes
- [ ] Any dependent changes have been merged and published in downstream modules

## Breaking Changes
If this introduces breaking changes:
- [ ] I have updated `CHANGELOG.md` with breaking change notices
- [ ] I have updated `package.json` version (semver)
- [ ] I have updated relevant documentation

## Performance Impact
- [ ] No performance impact
- [ ] Minor performance improvement (~X%)
- [ ] Potential performance impact (discussed below)

If performance impact: Explain the trade-offs and measurements.

## Migration Guide (if breaking)
If this is a breaking change, explain how users should migrate:

```
Before:
const thought = await shadowgraph.addThought(...)

After:
const thought = await shadowgraph.tools.addThought(...)
```

## Reviewer Notes
Any special considerations for code review?

---

**Before submitting:**
- [ ] PR title is descriptive and follows conventions
- [ ] Description clearly explains the change
- [ ] Tests are included and pass locally
- [ ] Documentation is updated (README, CHANGELOG, docs/)
- [ ] No merge conflicts
- [ ] Branch is up to date with `main`

**Thank you for contributing to ShadowGraph! 🎉**
