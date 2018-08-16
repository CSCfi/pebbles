app.controller('GroupsController', ['$q', '$scope', '$interval', '$uibModal', '$filter', 'AuthService', 'Restangular',
                          function ($q,   $scope,   $interval,   $uibModal,   $filter,   AuthService,   Restangular) {
        Restangular.setDefaultHeaders({token: AuthService.getToken()});
        $scope.include_deleted = false;
        $scope.includeRow = function(value, index) {
            if ($scope.include_deleted) {
                return true;
            } else {
                return !value.is_deleted;
            }
        };

        $scope.isAdmin = function() {
            return AuthService.isAdmin();
        };

        $scope.isGroupOwnerOrAdmin = function() {
            return AuthService.isGroupOwnerOrAdmin();
        };

        if (AuthService.isGroupOwnerOrAdmin()) {
            var groups = Restangular.all('groups');
            groups.getList().then(function (response) {
                $scope.groups = response;
            });

            var groupsSF = {};
            groupsSF.schema = {
                "type": "object",
                "title": "Comment",
                "properties": {
                    "name":  {
                    "title": "Group Name",
                    "type": "string",
                    "maxLength": 32,
                    "pattern": "^(?!(?:SYSTEM|System|system)).+",  // No case sensitive flag in schemaform
                    "validationMessage": "Required Field! Max length 32 chars",
                    },
                "description": {
                    "title": "Group Description",
                    "type": "string",
                    "maxLength": 250,
                    "validationMessage": "Maximum text limit for the description reached!"
                    }
                },
                "required": ["name"]

            }
            groupsSF.form = [
                {
                    "key": "name",
                    "type": "textfield",
                    "placeholder": "Group name"
                },
                {
                    "key": "description",
                    "type": "textarea",
                    "placeholder": "Details of the group"
                }
            ]

            $scope.openCreateGroupDialog=function() {
                $uibModal.open({
                    templateUrl: '/partials/modal_create_group.html',
                    controller: 'ModalCreateGroupController',
                    size: 'md',
                    resolve: {
                        groupsSF: function() {
                            return groupsSF;
                        },
                        groups: function() {
                            return groups;
                        }
                    }
                }).result.then(function() {
                     groups.getList().then(function (response) {
                         $scope.groups = response;
                      });
                });
            };

            $scope.openModifyGroupDialog=function(group) {
                $uibModal.open({
                    templateUrl: '/partials/modal_modify_group.html',
                    controller: 'ModalModifyGroupController',
                    size: 'md',
                    resolve: {
                        groupsSF: function() {
                            return groupsSF;
                        },
                        group: function() {
                            return group;
                        },
                        group_users: function() {
                            var group_users = Restangular.all('groups').one(group.id).all('users');
                            return group_users;
                        }
                    }
                }).result.then(function() {
                    groups.getList().then(function (response) {
                        $scope.groups = response;
                     });
                });
            };
 
           $scope.showUsers=function(group) {
               $uibModal.open({
		   templateUrl: '/partials/modal_showusers_group.html',
                   controller: 'ModalShowusersGroupController',
                    size: 'md',
                    resolve: {
                        group: function() {
                            return group;
                        },
                        group_users: function() {
                            var group_users = Restangular.all('groups').one(group.id).all('users');
                            return group_users;
                        }
                    }
               }).result.then(function() {
                    groups.getList().then(function (response) {
                        $scope.groups = response;
                     });
              });
           };

        }

    $scope.archiveGroup = function(group) {
        group.current_status = 'archived';
        group.patch().then(function() {
            groups.getList().then(function (response) {
                $scope.groups = response;
            }, function(response) {
                   if ('error' in response.data){
                   error_message = response.data.error;
                   }
                   $.notify({title: 'HTTP ' + response.status, message: error_message}, {type: 'danger'});
            });
        });
    };

    $scope.deleteGroup=function(group) {
        group.remove().then(function () {
            groups.getList().then(function (response) {
                        $scope.groups = response;
                     });
            $.notify({message: "Group: " + group.name + " is successfully deleted"}, {type: 'success'});
            }, function(response) {
                   if ('error' in response.data){
                      error_message = response.data.error;
                      $.notify({title: 'HTTP ' + response.status, message: error_message}, {type: 'danger'});
                   }
            });
    }

    $scope.clearUsersFromGroup = function(group) {
        var clearGroup = Restangular.oneUrl('groups/clear_users_from_group');
        var id = {'group_id': group.id};
        clearGroup.remove(id).then(function () {
            $.notify({message: "Cleared all users from Group: " + group.name}, {type: 'success'});
        }, function(response) {
            if ('error' in response.data){
               error_message = response.data.error;
               $.notify({title: 'HTTP ' + response.status, message: error_message}, {type: 'danger'});
            }
     });
    }

 }]);
app.controller('ModalCreateGroupController', function($scope, $modalInstance, groupsSF, groups) {

    $scope.groupsSF = groupsSF;
    groupsSF.model = {}

    $scope.createGroup = function(form, model) {
     if (form.$valid) {
            groups.post({ 
                 name: model.name, description: model.description,
            }).then(function () {
                $modalInstance.close(true);
            }, function(response) {
                error_message = 'unable to create group'
                if ('name' in response.data){
                    error_message = response.data.name
                }
                $.notify({title: 'HTTP ' + response.status, message: error_message}, {type: 'danger'});
            });
        }
    };

    $scope.cancel = function() {
        $modalInstance.dismiss('cancel');
    };
});

app.controller('ModalModifyGroupController', function($scope, $modalInstance, groupsSF, group, group_users) {

    $scope.groupsSF = groupsSF
    $scope.group = group;
    group_users.getList({'banned_list': true}).then(function (response) {
        $scope.userData = response;
    });
    group_users.getList().then(function (response) {
        $scope.managerData = response;
    });
    $scope.userSettings = {displayProp: 'email', scrollable: true, enableSearch: true};
    var old_name = group.name;

    $scope.modifyGroup = function(form, model, user_config) {
     if (form.$valid) {
            $scope.group.name = model.name
            $scope.group.description = model.description
            $scope.group.user_config = {
                 "banned_users": user_config.banned_users,
                 "managers": user_config.managers
            }
            $scope.group.put().then(function () {
                $modalInstance.close(true);
            }, function(response) {
                error_message = 'unable to create group';
                if ('name' in response.data){
                    error_message = response.data.name;
                    $scope.group.name = old_name;
                }
                if ('error' in response.data){
                    error_message = response.data.error;
                }
                $.notify({title: 'HTTP ' + response.status, message: error_message}, {type: 'danger'});
            });
        }
    };

    $scope.cancel = function() {
        $modalInstance.dismiss('cancel');
    };
});

app.controller('ModalShowusersGroupController', function($scope, $modalInstance, group, group_users) {
    group_users.getList().then(function (response) {
        $scope.group = group;
        $scope.userData = response;
        $scope.manageruser = _.flatten(_.map(group.user_config.managers, function(check_value){
                   return _.filter(response, check_value);
         }));
        $scope.groupowneruser = _.filter(response, {"is_group_owner": true} );
    });

    group_users.getList({'banned_list': true}).then(function (response) {
        $scope.managerData = response;
        $scope.banneduser = _.flatten(_.map(group.user_config.banned_users, function(check_value){
                   return _.filter(response, check_value);
        }));
    });

    $scope.cancel = function() {
        $modalInstance.dismiss('cancel');
    };
});
