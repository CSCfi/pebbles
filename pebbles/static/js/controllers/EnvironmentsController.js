app.controller('EnvironmentsController', ['$q', '$scope', '$http', '$interval', '$uibModal', 'AuthService', 'Restangular',
                               function ($q,   $scope,   $http,   $interval,   $uibModal,   AuthService,   Restangular) {

        $scope.isAdmin = function () {
            return AuthService.isAdmin();
        };

        $scope.getIcons = function () {
            if (AuthService.getIcons()) {
                return AuthService.getIcons()[3];
            } else {
                return false;
            }
        };

        Restangular.setDefaultHeaders({token: AuthService.getToken()});

        var templates = Restangular.all('environment_templates');

        templates.getList().then(function (response) {
            $scope.templates = response;
        });

        var environments = Restangular.all('environments');

        environments.getList({show_deactivated: true}).then(function (response) {
            $scope.environments = response;
        });

        var instances = Restangular.all('instances');

        var workspaces = Restangular.all('workspaces');

        workspaces.getList().then(function (response) {
            $scope.workspaces = response;
        });

        var importExportEnvironments = Restangular.all('import_export/environments');

        $scope.exportEnvironments = function () {

            importExportEnvironments.getList().then(function (response) {

                var jsonStr = JSON.stringify(response, null, 2); // Pretty print

                var blob = new Blob([jsonStr], {type: 'application/json'});
                var anchorLink = document.createElement('a');
                var mouseEvent = new MouseEvent('click');

                anchorLink.download = "environments.json";
                anchorLink.href = window.URL.createObjectURL(blob);
                anchorLink.dataset.downloadurl = ['text/json', anchorLink.download, anchorLink.href].join(':');
                anchorLink.dispatchEvent(mouseEvent);
            });
        };

        $scope.openImportEnvironmentsDialog = function () {
            $uibModal.open({
                templateUrl: '/partials/modal_import_environments.html',
                controller: 'ModalImportEnvironmentsController',
                resolve: {
                    importExportEnvironments: function () {
                        return importExportEnvironments;
                    },
                    environments: function () {
                        return environments;
                    }
                }
            }).result.then(function () {
                environments.getList().then(function (response) {
                    $scope.environments = response;
                });
            });
        };

        $scope.openCreateEnvironmentDialog = function (template) {
            $uibModal.open({
                templateUrl: '/partials/modal_create_environment.html',
                controller: 'ModalCreateEnvironmentController',
                resolve: {
                    template: function () {
                        return template;
                    },
                    environments: function () {
                        return environments;
                    },
                    workspaces_list: function () {
                        return $scope.workspaces;
                    }
                }
            }).result.then(function () {
                environments.getList().then(function (response) {
                    $scope.environments = response;
                });
            });
        };

        $scope.openReconfigureEnvironmentDialog = function (environment) {
            environment.get().then(function (response) {
                $uibModal.open({
                    templateUrl: '/partials/modal_reconfigure_environment.html',
                    controller: 'ModalReconfigureEnvironmentController',
                    resolve: {
                        environment: function () {
                            return environment;
                        },
                        workspaces_list: function () {
                            return $scope.workspaces;
                        }
                    }
                }).result.then(function () {
                    environments.getList().then(function (response) {
                        $scope.environments = response;
                    });
                });
            }, function (response) {
                if (response.status === 422) {
                    $.notify({
                        title: 'HTTP ' + response.status,
                        message: " Cannot reconfigure environment."
                    }, {type: 'danger'});
                }
            });
        };

        $scope.openEnvironmentLinkDialog = function (environment) {
            environment.get().then(function (response) {
                $uibModal.open({
                    size: 'lg',
                    templateUrl: '/partials/modal_url.html',
                    controller: 'ModalEnvironmentUrlController',
                    resolve: {
                        environment: environment
                    }
                });
            }, function (response) {
                if (response.status === 422) {
                    $.notify({
                        title: 'HTTP ' + response.status,
                        message: " Cannot get the link for environment."
                    }, {type: 'danger'});
                }
            });
        };

        $scope.copyEnvironment = function (environment) {
            var environment_copy = Restangular.all('environments').one('environment_copy', environment.id).put();
            environment_copy.then(function () {
                environments.getList().then(function (response) {
                    $.notify({
                        title: 'Success: ',
                        message: 'A copy of the environment was made'
                    }, {type: 'success'});
                    $scope.environments = response;
                });
            }, function (response) {
                $.notify({
                    title: 'HTTP ' + response.status,
                    message: 'Cannot copy environment'
                }, {type: 'danger'});
            });
        };

        $scope.archiveEnvironment = function (environment) {
            environment.current_status = 'archived';
            environment.patch().then(function () {
                environments.getList().then(function (response) {
                    $scope.environments = response;
                });
            });
        };

        $scope.deleteEnvironment = function (environment) {
            environment.get().then(function (response) {
                instances.getList().then(function (response) {
                    var environment_instances = _.filter(response, function (user) {
                        return user.environment_id === environment.id
                    });
                    $uibModal.open({
                        templateUrl: 'partials/modal_check_running_instance_confirm.html',
                        controller: 'ModalDeleteEnvironmentsController',
                        size: 'sm',
                        resolve: {
                            environment: function () {
                                return environment;
                            },
                            environment_instances: function () {
                                return environment_instances;
                            }
                        }
                    }).result.then(function () {
                        environments.getList().then(function (response) {
                            $scope.environments = response;
                        });
                    });
                });
            }, function (response) {
                $.notify({title: 'HTTP ' + response.status, message: " Cannot delete environment."}, {type: 'danger'});
            });
        };

        $scope.selectEnvironment = function (environment) {
            $scope.selectedEnvironment = environment;
            $scope.$broadcast('schemaFormRedraw');
        };

        $scope.updateConfig = function () {
            $scope.selectedEnvironment.put();
            $('#environmentConfig').modal('hide');
        };

        $scope.activate = function (environment) {
            environment.get().then(function (response) {
                environment.is_enabled = true;
                environment.put();
            }, function (response) {
                if (response.status === 422) {
                    $.notify({
                        title: 'HTTP ' + response.status,
                        message: 'Cannot activate environment'
                    }, {type: 'danger'});
                }
            });
        };

        $scope.deactivate = function (environment) {
            environment.get().then(function () {
                environment.is_enabled = undefined;
                environment.put();
            }, function (response) {
                if (response.status === 422) {
                    $.notify({
                        title: 'HTTP ' + response.status,
                        message: 'Cannot deactivate environment'
                    }, {type: 'danger'});
                }
            });
        };

    }]);


app.controller('ModalImportEnvironmentsController', function ($scope, $modalInstance, importExportEnvironments, environments) {

    $scope.importEnvironments = function (element) {

        $scope.isImportSuccess = false;
        $scope.isImportFailed = false;
        var errorResponse = "Indexes of environments which were not imported: ";
        var requestsCount = 0;
        var file = element.files[0];
        var reader = new FileReader();
        reader.onload = function () {
            $scope.$apply(function () {
                try {
                    // Read from the file and convert to JSON object
                    var environmentsJson = JSON.parse(String(reader.result));
                    var totalItems = environmentsJson.length;
                    for (var environmentIndex in environmentsJson) {
                        if (environmentsJson.hasOwnProperty(environmentIndex)) {
                            var environmentItem = environmentsJson[environmentIndex];
                            var obj = {
                                name: environmentItem.name,
                                config: environmentItem.config,
                                template_name: environmentItem.template_name,
                                workspace_name: environmentItem.workspace_name,
                                index: environmentIndex
                            };  // Send according to forms defined

                            importExportEnvironments.post(obj).then(function () {  // Post to the REST API
                                requestsCount++;
                                $scope.imported = true;
                                if (requestsCount === totalItems) {  // Check if all the requests were OK
                                    $scope.isImportSuccess = true;
                                }
                            }, function (response) {
                                // Attach the indices of environment items which are corrupt
                                errorResponse = errorResponse + response.config.data.index + ' ';
                                $.notify({
                                    title: 'HTTP ' + response.status,
                                    message: 'error:' + response.statusText
                                }, {type: 'danger'});
                                $scope.isImportFailed = true;
                                $scope.errorResponse = errorResponse;
                            });
                        }
                    }
                    if (totalItems === 0) {
                        $.notify({
                            title: 'Environments could not be imported!',
                            message: 'No environments found'
                        }, {type: 'danger'});
                    }
                } catch (exception) {
                    $.notify({
                        title: 'Environments could not be imported!',
                        message: exception
                    }, {type: 'danger'});
                }
            });
        };
        reader.readAsText(file);  // Fires the onload event defined above
    };

    $scope.done = function () {
        $modalInstance.close(true);
    };

    $scope.cancel = function () {
        $modalInstance.dismiss('cancel');
    };

});


app.controller('ModalCreateEnvironmentController', function ($scope, $modalInstance, template, environments, workspaces_list) {
    $scope.template = template;
    $scope.workspaces = workspaces_list;
    $scope.createEnvironment = function (form, model, workspaceModel) {
        $scope.$broadcast('schemaFormValidate');
        if (form.$valid) {
            environments.post({
                template_id: $scope.template.id,
                name: model.name,
                config: model,
                workspace_id: workspaceModel,
                lifespan_months: $scope.bpLifespanMonths
            }).then(function () {
                $modalInstance.close(true);
            }, function (response) {
                error_message = 'unable to create environment';
                if ('name' in response.data) {
                    error_message = response.data.name;
                } else if ('message' in response.data) {
                    error_message = response.data.message;
                }
                $.notify({title: 'HTTP ' + response.status, message: error_message}, {type: 'danger', z_index: 2000});
            });
        }
    };

    $scope.cancel = function () {
        $modalInstance.dismiss('cancel');
    };
});

app.controller('ModalReconfigureEnvironmentController', function ($scope, $modalInstance, environment, workspaces_list) {
    $scope.environment = environment;
    var config_mismatch = false;
    environment.get().then(function (response) {
        if (!_.isEqual($scope.environment['config'], response['config'])) {  // Object equality check
            alert('Environment configuration has been changed from the previous configuration');
            $scope.environment = response;
            config_mismatch = true; //Concurrency
        }
    });

    $scope.updateEnvironment = function (form, model) {
        if (form.$valid) {
            $scope.environment.config = model;
            //$scope.environment.workspace_id = workspaceModel.id;
            $scope.environment.put().then(function () {
                $modalInstance.close(true);
            }, function (response) {
                $.notify({
                    title: 'HTTP ' + response.status,
                    message: 'unable to reconfigure environment'
                }, {type: 'danger'});
            });
        }
    };


    $scope.cancel = function () {
        if (config_mismatch) {
            $modalInstance.close(true);  // launches the result section of modal
        }
        $modalInstance.dismiss('cancel');  // does not launch the result of modal
    };
});

app.controller('ModalEnvironmentUrlController', function ($scope, $modalInstance, environment) {

    $scope.url_type = "Environment Link (To be given to the users)" + ' - ' + environment.name;
    var hostname = window.location.hostname;
    $scope.url = 'https://' + hostname + '/#/environment/' + environment.id;

    $scope.cancel = function () {
        $modalInstance.dismiss('cancel');
    };
});


app.controller('ModalDeleteEnvironmentsController', function ($scope, $modalInstance, environment, environment_instances) {
    $scope.environment_instances = environment_instances;
    $scope.removeEnvironments = function () {
        environment.remove().then(function () {
            $.notify({message: "Environment: " + environment.name + " is successfully deleted"}, {type: 'success'});
            $modalInstance.close(true);
        }, function (response) {
            $.notify({
                title: 'HTTP ' + response.status,
                message: 'Unable to delete the environment: ' + environment.name
            }, {type: 'danger'});
            $modalInstance.close(true);
        });
    };

    $scope.cancel = function () {
        $modalInstance.dismiss('cancel');
    };
});
