:orphan:

.. This HOWTO is a bit sparse atm. and needs improvement. Hope we
   can find a real user to give feedback on this.

============================
Simple persistence in GitHub
============================

.. NOTE:: All data in Pebbles should be considered ephemeral.

In the future we have plans to offer medium-term storage between container
stops and starts but currently that is still in development. This means that
each user is responsible for their own persistence solution.

`Github <https://github.io/>`_ is a popular service offering `Git
<http://git-scm.org/>`_ version control for free for open source projects.
There are many alternatives such as `GitLab <https://about.gitlab.com/>`_,
which can be hosted on your own systems  in case GitHub is not suitable for
your use case.

1. To start using GitHub `create an account <https://github.com/join>`_.
2. After that optionally
   `create a new repository <https://help.github.com/articles/creating-a-new-repository/>`_
   or use an existing one
3. It is recommended that you enable `2FA Authentication
   <https://help.github.com/articles/about-two-factor-authentication/>`_
4. If you enabled 2FA authentication you'll need to `create an access token
   <https://help.github.com/articles/creating-an-access-token-for-command-line-use/>`_. Store this
   token in a safe place as you won't be able to see it again!
5. Start a Jupyter/RStudio notebook
6. Use the HTTPS URL for cloning your repository
    * when asked for password give your access token instead
7. Commit files to git as you would
    * you'll need to access token to push to the remote repository
