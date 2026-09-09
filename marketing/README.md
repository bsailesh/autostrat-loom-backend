# Marketing site

The static site served at https://autostrat.net.

- S3 bucket: autostrat-temp-site
- CloudFront distribution: E2ZCVTWM9KA4M8
- DNS: Cloudflare

This folder is the source of truth. Edit here, commit, then deploy.

## Deploying

Upload changed files individually, then invalidate:

    aws s3 cp marketing/index.html s3://autostrat-temp-site/index.html
    aws cloudfront create-invalidation --distribution-id E2ZCVTWM9KA4M8 --paths "/*"

Never use "aws s3 sync --delete" against this bucket unless you are certain
this folder is complete - it would delete anything not present locally.

## Notes

- The distribution has a custom error response sending unmatched paths to the
  homepage, so a bad URL lands on the site rather than an XML error.
- This site is separate from the product frontend, which lives in frontend/
  and deploys to the autostrat-app bucket