app.controller('WorkspacesController', ['$q', '$scope', '$interval', '$uibModal', '$filter', 'AuthService', 'Restangular',
                               function ($q,   $scope,   $interval,   $uibModal,   $filter,   AuthService,   Restangular) {
        Restangular.setDefaultHeaders({token: AuthService.getToken()});
        $scope.include_deleted = false;
        $scope.includeRow = function (value, index) {
            if ($scope.include_deleted) {
                return true;
            } else {
                return !value.is_deleted;
            }
        };

        $scope.toggleWorkspaceList = function () {

            $scope.toggleWorkspaceList = {
                panel_open: false
            };
        }

        $scope.selectedWorkspace = false;
        $scope.showCode = false;
        $scope.getSelectedWorkspace = function (workspace) {

            $scope.showCode = false;
            $scope.selectedWorkspace = workspace;

            $scope.toggleWorkspaceList = {
                panel_open: false
            };
        }

        $scope.toggleJoinCode = function () {
            if ($scope.showCode) {
                $scope.showCode = false;
            } else {
                $scope.showCode = true;
            }
        }

        $scope.removeWorkspaceDetails = function () {
            $scope.selectedWorkspace = false;
        };

        $scope.isAdmin = function () {
            return AuthService.isAdmin();
        };

        $scope.isWorkspaceOwnerOrAdmin = function () {
            return AuthService.isWorkspaceOwnerOrAdmin();
        };

        $scope.getIcons = function () {
            if (AuthService.getIcons()) {
                return AuthService.getIcons()[2];
            } else {
                return false;
            }
        };

        if (AuthService.isWorkspaceOwnerOrAdmin()) {
            var workspaces = Restangular.all('workspaces');
            workspaces.getList().then(function (response) {
                if (AuthService.isAdmin()) {
                    $scope.workspaces = response;
                }
                else {
                    // new api lists all accessible workspaces, in this list we are interested on the ones we own
                    $scope.workspaces = response.filter(x => x.owner_eppn === AuthService.getUserName());
                }
            });

            var workspacesSF = {};
            workspacesSF.schema = {
                "type": "object",
                "title": "Comment",
                "properties": {
                    "name": {
                        "title": "Workspace Name",
                        "type": "string",
                        "maxLength": 32,
                        "pattern": "^(?!(?:SYSTEM|System|system)).+",  // No case sensitive flag in schemaform
                        "validationMessage": "Required Field! Max length 32 chars",
                    },
                    "description": {
                        "title": "Workspace Description",
                        "type": "string",
                        "maxLength": 250,
                        "validationMessage": "Maximum text limit for the description reached!"
                    }
                },
                "required": ["name"]

            }
            workspacesSF.form = [
                {
                    "key": "name",
                    "type": "textfield",
                    "placeholder": "Workspace name"
                },
                {
                    "key": "description",
                    "type": "textarea",
                    "placeholder": "Details of the workspace"
                }
            ]

            $scope.openCreateWorkspaceDialog = function () {
                $uibModal.open({
                    templateUrl: '/partials/modal_create_workspace.html',
                    controller: 'ModalCreateWorkspaceController',
                    size: 'md',
                    resolve: {
                        workspacesSF: function () {
                            return workspacesSF;
                        },
                        workspaces: function () {
                            return workspaces;
                        }
                    }
                }).result.then(function () {
                    workspaces.getList().then(function (response) {
                        $scope.workspaces = response;
                    });
                });
            };

            $scope.openModifyWorkspaceDialog = function (workspace) {
                $uibModal.open({
                    templateUrl: '/partials/modal_modify_workspace.html',
                    controller: 'ModalModifyWorkspaceController',
                    size: 'md',
                    resolve: {
                        workspacesSF: function () {
                            return workspacesSF;
                        },
                        workspace: function () {
                            return workspace;
                        },
                        workspace_users: function () {
                            var workspace_users = Restangular.all('workspaces').one(workspace.id).all('list_users');
                            return workspace_users;
                        }

                    }
                }).result.then(function () {
                    workspaces.getList().then(function (response) {
                        $scope.workspaces = response;
                    });
                });
            };


            $scope.openChangeOwnerDialog = function (workspace) {
                $uibModal.open({
                    templateUrl: '/partials/modal_change_workspace_owner.html',
                    controller: 'ModalChangeWorkspaceOwnerController',
                    size: 'md',
                    resolve: {
                        workspacesSF: function () {
                            return workspacesSF;
                        },
                        workspace: function () {
                            return workspace;
                        },
                        user_list: function () {
                            var user_list = Restangular.all('users');
                            return user_list;
                        }

                    }
                }).result.then(function () {
                    workspaces.getList().then(function (response) {
                        $scope.workspaces = response;
                    });
                });
            };


            $scope.showUsers = function (workspace) {
                $uibModal.open({
                    templateUrl: '/partials/modal_showusers_workspace.html',
                    controller: 'ModalShowusersWorkspaceController',
                    size: 'md',
                    resolve: {
                        workspace: function () {
                            return workspace;
                        },
                        workspace_users: function () {
                            var workspace_users = Restangular.all('workspaces').one(workspace.id).all('list_users');
                            return workspace_users;
                        }
                    }
                }).result.then(function () {
                    workspaces.getList().then(function (response) {
                        $scope.workspaces = response;
                    });
                });
            };

        }

        $scope.archiveWorkspace = function (workspace) {
            workspace.current_status = 'archived';
            workspace.patch().then(function () {
                workspaces.getList().then(function (response) {
                    $scope.workspaces = response;
                }, function (response) {
                    if ('error' in response.data) {
                        error_message = response.data.error;
                    }
                    $.notify({title: 'HTTP ' + response.status, message: error_message}, {type: 'danger'});
                });
            });
        };

        $scope.deleteWorkspace = function (workspace) {
            workspace.remove().then(function () {
                workspaces.getList().then(function (response) {
                    $scope.workspaces = response;
                });
                $.notify({message: "Workspace: " + workspace.name + " is successfully deleted"}, {type: 'success'});
            }, function (response) {
                if ('error' in response.data) {
                    error_message = response.data.error;
                    $.notify({title: 'HTTP ' + response.status, message: error_message}, {type: 'danger'});
                }
            });
        }

        $scope.clearUsersFromWorkspace = function (workspace) {
            var clearWorkspace = Restangular.one('workspaces', workspace.id).oneUrl('clear_users');
            var id = {'workspace_id': workspace.id};
            clearWorkspace.post().then(function () {
                $.notify({message: "Cleared all users from Workspace: " + workspace.name}, {type: 'success'});
            }, function (response) {
                if ('error' in response.data) {
                    error_message = response.data.error;
                    $.notify({title: 'HTTP ' + response.status, message: error_message}, {type: 'danger'});
                }
            });
        }

    }]);
app.controller('ModalCreateWorkspaceController', function ($scope, $modalInstance, workspacesSF, workspaces) {

    $scope.workspacesSF = workspacesSF;
    workspacesSF.model = {}

    $scope.createWorkspace = function (form, model) {
        if (form.$valid) {
            workspaces.post({
                name: model.name, description: model.description,
            }).then(function () {
                $modalInstance.close(true);
            }, function (response) {
                error_message = 'unable to create workspace'
                if ('name' in response.data) {
                    error_message = response.data.name
                } else if ('message' in response.data) {
                    error_message = response.data.message
                }
                $.notify({title: 'HTTP ' + response.status, message: error_message}, {type: 'danger', z_index: 2000});
            });
        }
    };

    $scope.cancel = function () {
        $modalInstance.dismiss('cancel');
    };
});

app.controller('ModalModifyWorkspaceController', function ($scope, $modalInstance, workspacesSF, workspace, workspace_users) {

    $scope.workspacesSF = workspacesSF
    $scope.workspace = workspace;
    workspace_users.getList({'banned_list': true}).then(function (response) {
        $scope.userData = response;
    });
    workspace_users.getList().then(function (response) {
        $scope.managerData = response;
    });
    $scope.userSettings = {displayProp: 'eppn', scrollable: true, enableSearch: true};
    var old_name = workspace.name;

    $scope.modifyWorkspace = function (form, model, user_config) {
        if (form.$valid) {
            $scope.workspace.name = model.name
            $scope.workspace.description = model.description
            $scope.workspace.user_config = {
                "banned_users": user_config.banned_users,
                "managers": user_config.managers,
                "owner": user_config.owner
            }
            $scope.workspace.put().then(function () {
                $modalInstance.close(true);
            }, function (response) {
                error_message = 'unable to create workspace';
                if ('name' in response.data) {
                    error_message = response.data.name;
                    $scope.workspace.name = old_name;
                }
                if ('error' in response.data) {
                    error_message = response.data.error;
                }
                $.notify({title: 'HTTP ' + response.status, message: error_message}, {type: 'danger'});
            });
        }
    };

    $scope.cancel = function () {
        $modalInstance.dismiss('cancel');
    };
});

app.controller('ModalChangeWorkspaceOwnerController', function ($scope, $modalInstance, workspacesSF, workspace, user_list) {

    $scope.workspacesSF = workspacesSF
    $scope.workspace = workspace;
    user_list.getList().then(function (response) {
        $scope.userData = _.filter(response, ['is_workspace_owner', true]);
    });


    var old_name = workspace.name;
    $scope.userSettings = {displayProp: 'eppn', scrollable: true, enableSearch: true, selectionLimit: '1'};

    $scope.confirmNewWorkspaceOwner = function (form, model, user_config) {

        if (form.$valid) {
            $scope.workspace.name = model.name
            $scope.workspace.description = model.description
            $scope.workspace.user_config = {
                "banned_users": user_config.banned_users,
                "managers": user_config.managers,
                "owner": user_config.owner
            }

            $scope.workspace.put().then(function () {
                $modalInstance.close(true);
            }, function (response) {
                error_message = 'unable to create workspace';
                if ('name' in response.data) {
                    error_message = response.data.name;
                    $scope.workspace.name = old_name;
                }
                if ('error' in response.data) {
                    error_message = response.data.error;
                }
                $.notify({title: 'HTTP ' + response.status, message: error_message}, {type: 'danger'});
            });
        }
    };

    $scope.cancel = function () {
        $modalInstance.dismiss('cancel');
    };
});


app.controller('ModalShowusersWorkspaceController', function ($scope, $modalInstance, workspace, workspace_users) {
    workspace_users.getList().then(function (response) {
        $scope.workspace = workspace;
        $scope.userData = response;
        $scope.manageruser = _.flatten(_.map(workspace.user_config.managers, function (check_value) {
            return _.filter(response, check_value);
        }));
        $scope.workspaceowneruser = _.filter(response, {"is_workspace_owner": true});
    });

    workspace_users.getList({'banned_list': true}).then(function (response) {
        $scope.managerData = response;
        $scope.banneduser = _.flatten(_.map(workspace.user_config.banned_users, function (check_value) {
            return _.filter(response, check_value);
        }));
    });

    $scope.cancel = function () {
        $modalInstance.dismiss('cancel');
    };
});

