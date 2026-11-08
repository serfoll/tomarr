# Contributing

Tomarr is a self-hosted *arr for manga, manhwa and webtoons. Before you start, read `CONTEXT/PRODUCT.md` for what is in scope and `CONTEXT/CONTEXT.md` for the terms the code and docs use. Past decisions are in `docs/adr/`, and the [open issues](https://github.com/serfoll/tomarr/issues) show what is planned.

## Sign your commits

Contributions are accepted under the [Developer Certificate of Origin](https://developercertificate.org/) (DCO). Every commit needs a line like this in its message:

```
Signed-off-by: Your Name <you@example.com>
```

`git commit -s` adds it from your `user.name` and `user.email`. The email must be the one you commit with, because the check compares the two. Signing off means you certify this text:

```text
Developer Certificate of Origin
Version 1.1

Copyright (C) 2004, 2006 The Linux Foundation and its contributors.

Everyone is permitted to copy and distribute verbatim copies of this
license document, but changing it is not allowed.


Developer's Certificate of Origin 1.1

By making a contribution to this project, I certify that:

(a) The contribution was created in whole or in part by me and I
    have the right to submit it under the open source license
    indicated in the file; or

(b) The contribution is based upon previous work that, to the best
    of my knowledge, is covered under an appropriate open source
    license and I have the right under that license to submit that
    work with modifications, whether created in whole or in part
    by me, under the same open source license (unless I am
    permitted to submit under a different license), as indicated
    in the file; or

(c) The contribution was provided directly to me by some other
    person who certified (a), (b) or (c) and I have not modified
    it.

(d) I understand and agree that this project and the contribution
    are public and that a record of the contribution (including all
    personal information I submit with it, including my sign-off) is
    maintained indefinitely and may be redistributed consistent with
    this project or the open source license(s) involved.
```

You keep the copyright on your contribution, and it is licensed under AGPL-3.0, the project's license.

## The check

A workflow named `dco` runs on every pull request. It looks at each commit, skips merge commits, and fails if a commit has no `Signed-off-by` line with the same email as the commit's author. For each failing commit it prints the short SHA, the subject and the fix. Pull requests opened by the repository owner are exempt.

To fix the last commit, run `git commit --amend -s` and force-push your branch. To fix every commit on your branch, run `git rebase --signoff HEAD~N`, where N is the number of commits in your pull request (its page shows the count), and force-push it. Only force-push a branch of your own.
