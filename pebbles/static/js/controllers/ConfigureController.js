app.controller('ConfigureController', ['$q', '$scope', '$http', '$interval', '$uibModal', 'AuthService', 'Restangular',
                              function ($q,   $scope,   $http,   $interval,   $uibModal,   AuthService,   Restangular) {

        Restangular.setDefaultHeaders({token: AuthService.getToken()});

        var plugins = Restangular.all('plugins');

        plugins.getList().then(function (response) {
            $scope.plugins = response;
        });

        var templates = Restangular.all('blueprint_templates');

        templates.getList({show_deactivated: true}).then(function (response) {
            $scope.templates = response;
        });


        var notifications = Restangular.all('notifications');
        var updateNotificationList = function() {
            notifications.getList({show_all: true}).then(function (response){
                $scope.notifications = response;
            });
        };
        updateNotificationList();


        var importExportTemplates = Restangular.all('import_export/blueprint_templates');

        $scope.exportTemplates = function () {

            importExportTemplates.getList().then(function(response) {

                var jsonStr = JSON.stringify(response, null, 2); // Pretty print

                var blob = new Blob([jsonStr], {type: 'application/json'});
                var anchorLink = document.createElement('a');
                var mouseEvent = new MouseEvent('click');

                anchorLink.download = "blueprint_templates.json";
                anchorLink.href = window.URL.createObjectURL(blob);
                anchorLink.dataset.downloadurl = ['text/json', anchorLink.download, anchorLink.href].join(':');
                anchorLink.dispatchEvent(mouseEvent);
            });
        };

        $scope.openImportTemplatesDialog = function() {
            $uibModal.open({
                templateUrl: '/partials/modal_import_templates.html',
                controller: 'ModalImportTemplatesController',
                resolve: {
                    importExportTemplates: function() {
                        return importExportTemplates;
                    },
                    templates: function() {
                        return templates;
                    }
               }
            }).result.then(function() {
                   templates.getList().then(function (response) {
                   $scope.templates = response;
                   });
               });
        };

        $scope.openCreateTemplateDialog = function(plugin) {
            $uibModal.open({
                templateUrl: '/partials/modal_create_template.html',
                controller: 'ModalCreateTemplateController',
                resolve: {
                    plugin: function() {
                        return plugin;
                    },
                    templates: function() {
                        return templates;
                    }
                }
            }).result.then(function() {
                templates.getList().then(function (response) {
                    $scope.templates = response;
                });
            });
        };

        $scope.openReconfigureTemplateDialog = function(template) {
            $uibModal.open({
                templateUrl: '/partials/modal_reconfigure_template.html',
                controller: 'ModalReconfigureTemplateController',
                resolve: {
                    template: function() {
                        return template;
                    }
                }
            }).result.then(function() {
                templates.getList().then(function (response) {
                    $scope.templates = response;
                });
            });
        };


        $scope.copyTemplate = function(template) {
            var template_copy = Restangular.all('blueprint_templates').one('template_copy', template.id).put();
            template_copy.then(function () {
                templates.getList().then(function (response) {
                      $.notify({
                          title: 'Success: ',
                          message: 'A copy of the blueprint template was made'
                          }, {type: 'success'});
                    $scope.templates = response;
                });
            });
        }, function (response) {
               $.notify({
                   title: 'HTTP ' + response.status,
                   message: 'Could not copy blueprint template'
               }, {type: 'danger'});

        };


        $scope.deleteNotification = function(notification) {
            notification.remove().then(function() {
                updateNotificationList();
            });
        };

        $scope.selectTemplate = function(template) {
            $scope.selectedTemplate = template;
            $scope.$broadcast('schemaFormRedraw');
        };

        $scope.updateConfig = function() {
            $scope.selectedTemplate.put();
            $('#templateConfig').modal('hide');
        };

        $scope.activate = function (template) {
            template.is_enabled = true;
            template.put();
        };

        $scope.deactivate = function (template) {
            $uibModal.open({
                templateUrl: '/partials/modal_disable_blueprints.html',
                controller: 'ModalDisableBlueprintsController',
                size: 'sm',
                resolve: {
                    template: function() {
                        return template;
                    }
                }
            })

            template.is_enabled = undefined;
            template.put();
        };

        $scope.openCreateNotification= function() {
            $uibModal.open({
                templateUrl: '/partials/modal_create_notification.html',
                controller: 'ModalCreateNotificationController',
                size: 'sm',
                resolve: {
                    notifications: function() {
                        return notifications;
                    }
                }
            }).result.then(function() {
                updateNotificationList()
            });
        };

        $scope.emailNotification = function(notification) {
            notification.patch({send_mail: true}).then(function(response) {
            });
        };

        $scope.openEditNotification = function(notification) {
            $uibModal.open({
                templateUrl: '/partials/modal_edit_notification.html',
                controller: 'ModalEditNotificationController',
                size: 'sm',
                resolve: {
                    notification: function() {
                        return notification;
                    }
                }
            }).result.then(function() {
                updateNotificationList();
            });
        };

    }]);



app.controller('ModalImportTemplatesController', function($scope, $modalInstance, importExportTemplates, templates)
{

    $scope.importTemplates = function(element) {

        $scope.isImportSuccess = false;
        $scope.isImportFailed = false;
        var errorResponse = "Indexes of templates which were not imported: ";
        var requestsCount = 0;
        var file = element.files[0];
        var reader = new FileReader();
        reader.onload = function() {
            $scope.$apply(function() {
                try {
                    // Read from the file and convert to JSON object
                    var templatesJson = JSON.parse(String(reader.result));
                    var totalItems = templatesJson.length;
                    for (var templateIndex in templatesJson) {
                        if (templatesJson.hasOwnProperty(templateIndex)) {
                            var templateItem = templatesJson[templateIndex];
                            var obj = {
                                name: templateItem.name,
                                config: templateItem.config,
                                plugin_name: templateItem.plugin_name,
                                allowed_attrs: {'allowed_attrs': templateItem.allowed_attrs},  // WTForms needs dict
                                index: templateIndex
                            };  // Send according to forms defined

                            importExportTemplates.post(obj).then(function () {  // Post to the REST API
                                requestsCount++;
                                $scope.imported = true;
                                if (requestsCount == totalItems) {  // Check if all the requests were OK
                                    $scope.isImportSuccess = true;
                                }
                            }, function (response) {
                                 // Attach the indices of template items which are corrupt
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
                                    title: 'Blueprint Templates could not be imported!',
                                    message: 'No templates found'
                                }, {type: 'danger'});
                    }
                }
                catch(exception){
                    $.notify({
                        title: 'Blueprint Templates could not be imported!',
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


app.controller('ModalCreateTemplateController', function($scope, $modalInstance, plugin, templates) {
    $scope.plugin = plugin;
    var attrsData = Object.keys(plugin.schema.properties);
    attrsData = attrsData.filter(function(attr){ return !['name', 'description'].includes(attr)});
    $scope.attrsData =  _(attrsData).map(function(attr){ return {'id': attr} }).value(); // Data for angular multiselect
    $scope.attrsModel = []
    $scope.attrsSettings = {displayProp: 'id', scrollable: true, enableSearch: true};

    $scope.createTemplate = function(form, model, attrsModel) {
        if (form.$valid) {
            attrsModel = _(attrsModel).map(function(attr){ return attr.id }).value();  // Get the data back as an array of attrs
            var allowed_attrs = {'allowed_attrs': attrsModel} // Sending array in an obj, Only to please WTForms
            templates.post({ plugin: $scope.plugin.id, name: model.name, config: model, allowed_attrs: allowed_attrs}).then(function () {
                $modalInstance.close(true);
            }, function(response) {
                $.notify({title: 'HTTP ' + response.status, message: 'unable to create blueprint template'}, {type: 'danger'});
            });
        }
    };

    $scope.cancel = function() {
        $modalInstance.dismiss('cancel');
    };
});

app.controller('ModalReconfigureTemplateController', function($scope, $modalInstance, template) {
    $scope.template = template;
    var attrsData = Object.keys(template.schema.properties);
    $scope.attrsData =  _(attrsData).map(function(attr){ return {'id': attr} }).value(); // Data for angular multiselect
    var attrsModel = template.allowed_attrs;
    $scope.attrsModel = _(attrsModel).map(function(attr){ return {'id': attr} }).value(); 
    $scope.attrsSettings = {displayProp: 'id', scrollable: true, enableSearch: true};

    $scope.updateTemplate = function(form, model, attrsModel) {
        if (form.$valid) {
            $scope.template.config = model;
            attrsModel = _(attrsModel).map(function(attr){ return attr.id }).value();  // Get the data back as an array of attrs
            var allowed_attrs = {'allowed_attrs': attrsModel} // Sending array in an obj, Only to please WTForms
            $scope.template.allowed_attrs = allowed_attrs;
            $scope.template.put().then(function () {
                $modalInstance.close(true);
            }, function(response) {
                $.notify({title: 'HTTP ' + response.status, message: 'unable to reconfigure blueprint template'}, {type: 'danger'});
            });
        }
    };

    $scope.cancel = function() {
        $modalInstance.dismiss('cancel');
    };
});

app.controller('ModalCreateNotificationController', function($scope, $modalInstance, notifications) {
    $scope.createNotification = function(notification) {
        notifications.post({ subject: notification.subject, message: notification.message }).then(function () {
            $modalInstance.close(true);
        }, function(response) {
            $.notify({title: 'HTTP ' + response.status, message: 'unable to create notification'}, {type: 'danger'});
        });
    };

    $scope.cancel = function() {
        $modalInstance.dismiss('cancel');
    };
});

app.controller('ModalEditNotificationController', function($scope, $modalInstance, Restangular, notification) {
    $scope.notification = Restangular.copy(notification);
    $scope.notification.subject = notification.subject;
    $scope.notification.message = notification.message;

    $scope.editNotification = function(notification) {
        notification.subject = $scope.notification.subject;
        notification.message = $scope.notification.message;

        notification.put().then(function() {
            $modalInstance.close(true);
        }, function(response) {
            $.notify({title: 'HTTP ' + response.status, message: 'unable to edit notification'}, {type: 'danger'});
        });
    };

    $scope.cancel = function() {
        $modalInstance.dismiss('cancel');
    };
});

app.controller('ModalDisableBlueprintsController', function($scope, $modalInstance, template) {
    $scope.disableBlueprints = function() {
        template.put({'disable_blueprints': true}).then(function () {
            $modalInstance.close(true);
        }, function(response) {
            $.notify({title: 'HTTP ' + response.status, message: 'unable to deactivate'}, {type: 'danger'});
        });
    };

    $scope.cancel = function() {
        $modalInstance.dismiss('cancel');
    };
});
