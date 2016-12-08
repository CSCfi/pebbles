:orphan:

Group Owner's Guide
*******************

Groups give you more control and flexiblity to manage your blueprints for
different sets of users.  A group can contain multiple blueprints and multiple
users in it. Each blueprint that you create based on a given template would
require a mandatory group to associate it with. Hence, the blueprints would
only visible to the users belonging to a specific group.

A group can be joined only if the user has a valid joining code. Upon joining,
he can see the list of blueprints associated with that group.  A group can only
have a single owner i.e. the one who has created the group but it can have
multiple "managers".  If a user is banned from a group, he can no longer see
the blueprints of the said group.  A user is allowed to leave the group if he
wants.

A group owner can perform the following operations:

* create a new group or modify the existing group
* add or remove group managers
* ban or unban a user
* create and modify blueprints on a group which he owns or manages
* check and delete the instances of users running on their groups' blueprints
* launch instances using his groups' blueprints

A group owner can always be a group manager for a group which he doesn't own,
provided he is been appointed to be one.  Similarly, he can also be a normal
user in a group which he doesn't own, provided he has a valid joining code for
a group.


The group manager has slightly less priviledges as compared to group owner. A 
group manager *cannot create or modify an existing group*.
They however have the following rights:

* create and modify blueprints on a group for which they have a right to manage
* check and delete the instances of users running on their groups' blueprints
* launch instances using his managed groups' blueprints

A group manager is always one of the users of the groups that he manages. He
can also join other groups as a normal user if he has a joining code.

A regular user can do the following things on a Pebbles instance:

* Join and exit a group
* Run an instance based on the blueprints belonging to his groups
* Destroy an instance they started earlier


Instructions
------------

**Creating a Group:**

1) Go the Groups tab

2) Click on create group button. Give a name and description.

**Adding a manager and banning users**

1) Once the user has joined , click on modify group
2) Select the user(s) in the banned users / managers multiselct component accordingly.

**Creating a blueprint:**

1) Click on Blueprints tab

2) You will see a list of templates that admin has created for you to choose from. From any one of the template, click on Click Blueprint

3) Then choose the group which you want the blueprint to be associated with, enter the name , description and other properties which you see (if you want to override the default values)

4) Click on Activate to activate the blueprint for the users

.. should this be for users instead?

**To Join A Group:**

1) Go to Accounts tab -> Join Group
2) Enter the code provided by group admin or manager

**To Leave A Group:**

1) Go to Accounts tab
2) From the list of groups , click on Exit Group for any of the groups


Github persistence
------------------

See :doc:`github_persistence`
