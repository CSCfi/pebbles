app.controller('BlueprintsController', ['$q', '$scope', '$http', '$interval', '$uibModal', 'AuthService', 'Restangular',
                              function ($q,   $scope,   $http,   $interval,   $uibModal,   AuthService,   Restangular) {

        Restangular.setDefaultHeaders({token: AuthService.getToken()});

        var templates = Restangular.all('blueprint_templates');

        templates.getList().then(function (response) {
            $scope.templates = response;
        });

        var blueprints = Restangular.all('blueprints');

        blueprints.getList({show_deactivated: true}).then(function (response) {
            $scope.blueprints = response;
        });

         var groups = Restangular.all('groups');

         groups.getList().then(function (response) {
             $scope.groups = response;
         });

        var importExportBlueprints = Restangular.all('import_export/blueprints');

        $scope.exportBlueprints = function () {

            importExportBlueprints.getList().then(function(response) {

                var jsonStr = JSON.stringify(response, null, 2); // Pretty print

                var blob = new Blob([jsonStr], {type: 'application/json'});
                var anchorLink = document.createElement('a');
                var mouseEvent = new MouseEvent('click');

                anchorLink.download = "blueprints.json";
                anchorLink.href = window.URL.createObjectURL(blob);
                anchorLink.dataset.downloadurl = ['text/json', anchorLink.download, anchorLink.href].join(':');
                anchorLink.dispatchEvent(mouseEvent);
            });
        };

        $scope.openImportBlueprintsDialog = function() {
            $uibModal.open({
                templateUrl: '/partials/modal_import_blueprints.html',
                controller: 'ModalImportBlueprintsController',
                resolve: {
                    importExportBlueprints: function() {
                        return importExportBlueprints;
                    },
                    blueprints: function() {
                        return blueprints;
                    }
               }
            }).result.then(function() {
                   blueprints.getList().then(function (response) {
                   $scope.blueprints = response;
                   });
               });
        };

        $scope.openCreateBlueprintDialog = function(template) {
            $uibModal.open({
                templateUrl: '/partials/modal_create_blueprint.html',
                controller: 'ModalCreateBlueprintController',
                resolve: {
                    template: function() {
                        return template;
                    },
                    blueprints: function() {
                        return blueprints;
                    },
                    groups_list: function() {
                        return $scope.groups;
                    }
                }
            }).result.then(function() {
                blueprints.getList().then(function (response) {
                    $scope.blueprints = response;
                });
            });
        };

        $scope.openReconfigureBlueprintDialog = function(blueprint) {
            $uibModal.open({
                templateUrl: '/partials/modal_reconfigure_blueprint.html',
                controller: 'ModalReconfigureBlueprintController',
                resolve: {
                    blueprint: function() {
                        return blueprint;
                    },
                    groups_list: function() {
                        return $scope.groups;
                    }
                }
            }).result.then(function() {
                blueprints.getList().then(function (response) {
                    $scope.blueprints = response;
                });
            });
        };


        $scope.deleteNotification = function(notification) {
            notification.remove().then(function() {
                updateNotificationList();
            });
        };

        $scope.selectBlueprint = function(blueprint) {
            $scope.selectedBlueprint = blueprint;
            $scope.$broadcast('schemaFormRedraw');
        };

        $scope.updateConfig = function() {
            $scope.selectedBlueprint.put();
            $('#blueprintConfig').modal('hide');
        };

        $scope.activate = function (blueprint) {
            blueprint.is_enabled = true;
            blueprint.put();
        };

        $scope.deactivate = function (blueprint) {
            blueprint.is_enabled = undefined;
            blueprint.put();
        };

    }]);



app.controller('ModalImportBlueprintsController', function($scope, $modalInstance, importExportBlueprints, blueprints)
{

    $scope.importBlueprints = function(element) {

        $scope.isImportSuccess = false;
        $scope.isImportFailed = false;
        var errorResponse = "Indexes of blueprints which were not imported: ";
        var requestsCount = 0;
        var file = element.files[0];
        var reader = new FileReader();
        reader.onload = function() {
            $scope.$apply(function() {
                try {
                    // Read from the file and convert to JSON object
                    var blueprintsJson = JSON.parse(String(reader.result));
                    var totalItems = blueprintsJson.length;
                    for (var blueprintIndex in blueprintsJson) {
                        if (blueprintsJson.hasOwnProperty(blueprintIndex)) {
                            var blueprintItem = blueprintsJson[blueprintIndex];
                            var obj = {
                                name: blueprintItem.name,
                                config: blueprintItem.config,
                                plugin_name: blueprintItem.plugin_name,
                                index: blueprintIndex
                            };  // Send according to forms defined

                            importExportBlueprints.post(obj).then(function () {  // Post to the REST API
                                requestsCount++;
                                $scope.imported = true;
                                if (requestsCount == totalItems) {  // Check if all the requests were OK
                                    $scope.isImportSuccess = true;
                                }
                            }, function (response) {
                                 // Attach the indices of blueprint items which are corrupt
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
                    if(totalItems == 0){
                        $.notify({
                                    title: 'Blueprints could not be imported!',
                                    message: 'No blueprints found'
                                }, {type: 'danger'});
                    }
                }
                catch(exception){
                    $.notify({
                        title: 'Blueprints could not be imported!',
                        message: exception
                    }, {type: 'danger'});
                }
            });
        };
        reader.readAsText(file);  // Fires the onload event defined above
    };

    $scope.done = function() {
        $modalInstance.close(true);
    };

    $scope.cancel = function() {
        $modalInstance.dismiss('cancel');
    };

});


app.controller('ModalCreateBlueprintController', function($scope, $modalInstance, template, blueprints, groups_list) {
    $scope.template = template;
    $scope.groups = groups_list;
    console.log($scope.groups);
    console.log($scope.template.id);
    $scope.createBlueprint = function(form, model, groupModel) {
        if (form.$valid) {
            blueprints.post({ template_id: $scope.template.id, name: model.name, config: model, group_id:  groupModel}).then(function () {
                $modalInstance.close(true);
            }, function(response) {
                $.notify({title: 'HTTP ' + response.status, message: 'unable to create blueprint'}, {type: 'danger'});
            });
        }
    };

    $scope.cancel = function() {
        $modalInstance.dismiss('cancel');
    };
});

app.controller('ModalReconfigureBlueprintController', function($scope, $modalInstance, blueprint, groups_list) {
    $scope.blueprint = blueprint;
    $scope.groups = groups_list;
    $scope.groupModel = blueprint.group_id;
    $scope.updateBlueprint = function(form, model, groupModel) {
        if (form.$valid) {
            $scope.blueprint.config = model;
            $scope.blueprint.group_id = groupModel;
            $scope.blueprint.put().then(function () {
                $modalInstance.close(true);
            }, function(response) {
                $.notify({title: 'HTTP ' + response.status, message: 'unable to reconfigure blueprint'}, {type: 'danger'});
            });
        }
    };

    $scope.cancel = function() {
        $modalInstance.dismiss('cancel');
    };
});
