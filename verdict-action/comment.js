// Post or update the Verdict PR comment, found by the hidden marker on its first line.
// A skipped run only updates an existing comment; it never adds a new one.
const fs = require('fs');

const MARKER = '<!-- verdict-diff -->';

module.exports = async ({ github, context, core }) => {
  const body = fs.readFileSync(process.env.VERDICT_MD, 'utf8');
  const skipped = process.env.VERDICT_STATUS === 'skipped';
  const { owner, repo } = context.repo;
  const issue_number = context.payload.pull_request.number;

  try {
    const comments = await github.paginate(github.rest.issues.listComments, {
      owner, repo, issue_number, per_page: 100,
    });
    const existing = comments.find((c) => c.body?.startsWith(MARKER));

    if (existing) {
      await github.rest.issues.updateComment({ owner, repo, comment_id: existing.id, body });
      core.info(`Updated Verdict comment ${existing.html_url}`);
    } else if (!skipped) {
      const { data } = await github.rest.issues.createComment({ owner, repo, issue_number, body });
      core.info(`Posted Verdict comment ${data.html_url}`);
    } else {
      core.info('Skipped run and no existing comment; not commenting.');
    }
  } catch (err) {
    // Fork PRs get a read-only token. The result is still in the job summary.
    core.warning(`Could not post the Verdict comment (${err.status || ''} ${err.message}).`);
  }
};
