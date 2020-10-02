:orphan:

Workspace Owner's Guide
***********************

**PLEASE NOTE (if you're using CSC Notebooks): notebooks.csc.fi has a regular scheduled maintenance downtime on first Tuesday of every month between 7-9 AM**

Workspaces give you more control and flexiblity to manage your environments for
different sets of users.  A workspace can contain multiple environments and multiple
users in it. Each environment that you create based on a given template would
require a mandatory workspace to associate it with. Hence, the environments would
only visible to the users belonging to a specific workspace.

A workspace can be joined only if the user has a valid joining code. Upon joining,
he can see the list of environments associated with that workspace.  A workspace can only
have a single owner i.e. the one who has created the workspace but it can have
multiple "managers".  If a user is banned from a workspace, he can no longer see
the environments of the said workspace.  A user is allowed to leave the workspace if he
wants.

A workspace owner can perform the following operations:

* create a new workspace or modify the existing workspace
* add or remove workspace managers
* ban or unban a user
* create and modify environments on a workspace which he owns or manages
* check and delete the instances of users running on their workspaces' environments
* launch instances using his workspaces' environments

A workspace owner can always be a workspace manager for a workspace which he doesn't own,
provided he is been appointed to be one.  Similarly, he can also be a normal
user in a workspace which he doesn't own, provided he has a valid joining code for
a workspace.


The workspace manager has slightly less priviledges as compared to workspace owner. A 
workspace manager *cannot create or modify an existing workspace*.
They however have the following rights:

* create and modify environments on a workspace for which they have a right to manage
* check and delete the instances of users running on their workspaces' environments
* launch instances using his managed workspaces' environments

A workspace manager is always one of the users of the workspaces that he manages. He
can also join other workspaces as a normal user if he has a joining code.

A regular user can do the following things on a Pebbles instance:

* Join and exit a workspace
* Run an instance based on the environments belonging to his workspaces
* Destroy an instance they started earlier


Instructions for creating a workspace and its environment
---------------------------------------------------

**Creating a Workspace:**

1) Go the Workspaces tab

2) Click on 'Create A New Workspace' button. Give a name and description.

.. image:: img/workspace_create.png

3) You should be able to see the workspace in your workspaces list now. The joining
code for a workspace is the code that you'll mail or otherwise communicate to the
users who wish to join your workspace.

.. image:: img/workspace_view.png

Next step would be to create a environment for your workspace.

**Creating a environment:**

Note: The instructions below details creating a environment based on existing/admin provided docker images. If you wish to create your own customized docker image
(`See instructions for custom images through openshift driver <https://github.com/csc-training/geocomputing/tree/master/rahti>`_)


1. Click on Environments tab

2. You will see a list of templates that admin has created for you to choose
from. From any one of the template, click on Create Environment

.. image:: img/environment_create.png

3. Then choose the workspace which you want the environment to be associated with,
enter the name , description and other properties which you see (if you want
to override the default values)

4. **Set time limit for your environment** : You can choose to override the *maximum lifetime* field
(If your template permits it), to suit your course needs. **NOTE: Please do not enter a value
more than 8h-10h** (the environments should not be run for more than a day, in case
of multiple day trainings - launch it on a daily basis)

5. **IMPORTANT STEP** : Provide Environment Variables in the field *environment variables for docker* - 
**This step allows you to fetch your own github repo (containing your files, datasets), 
install custom libraries etc , for your environments.**
So, when a user launches your environment, they will be able to see the files from your github repo and
the necessary libraries directly.
In order to continue with this, you need to enter the following value in the field called 
'environment variables for docker, separated by space' :
``AUTODOWNLOAD_URL=<URL_TO_A_BASH_SCRIPT> AUTODOWNLOAD_EXEC=<BASH_SCRIPT_FILENAME>.bash``

As you can notice, it requires ``<URL_TO_A_BASH_SCRIPT>``. This bash script is responsible for cloning your github repo,
installing your libraries etc. 
An example of the bash script can be found at : https://github.com/CSCfi/notebook-images/blob/master/bootstrap/spark-sql.bash
The above script tries to clone a github repo and then tries to install a python library via pip. The github repo it clones
contains the required files and datasets. You can make your own script in a similar way and host it somewhere on the web.
Replace ``<URL_TO_A_BASH_SCRIPT>`` with the actual URL of your script.

.. image:: img/environments_view.png

6) Click on Activate button (in the environments list) to activate the
environment. Now, the users will be able to see the environments.



Instructions for Users who wish to join or leave a workspace
--------------------------------------------------------

**To Join A Workspace:**

1) Go to Accounts tab -> Join Workspace 2) Enter the code provided by workspace admin
or manager

.. image:: img/workspace_join.png

**To Leave A Workspace:**

1) Go to Accounts tab 2) From the list of workspaces , click on Exit Workspace for any
of the workspaces


**Adding extra managers and banning users (OPTIONAL)**

1) Once the user has joined , click on modify workspace 2) Select the user(s) in
the banned users / managers multiselct component accordingly.

Github persistence
------------------

See :doc:`github_persistence`
