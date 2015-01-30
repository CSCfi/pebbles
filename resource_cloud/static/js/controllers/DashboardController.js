app.controller('DashboardController', ['$scope', '$routeParams', '$interval', 'AuthService', 'Restangular',
    function ($scope, $routeParams, $interval, AuthService, Restangular) {

        Restangular.setDefaultHeaders({token: AuthService.getToken()});

        if (AuthService.isAdmin()) {
            var users = Restangular.all('users');
            users.getList().then(function (response) {
                $scope.users = response;
            });

            $scope.new_user = '';
            $scope.add_user = function (email) {
                var user_parameters = {email: email};
                if (email) {
                    users.post(user_parameters).then(function (response) {
                        $scope.users.push(response);
                    });
                }
            }

            $scope.remove_user = function (user) {
                user.remove().then(function () {
                    var index = $scope.users.indexOf(user);
                    if (index > -1) $scope.users.splice(index, 1);
                });
            }
        }

        var resources = Restangular.all('resources');
        resources.getList().then(function (response) {
            $scope.services = response;
        });

        var provisionedResources = Restangular.all('provisioned_resources');
        provisionedResources.getList().then(function (response) {
            $scope.instances = response;
        });

        $scope.provision = function (resource) {
            resource.post().then(function (response) {
                    provisionedResources.getList().then(function (response) {
                            $scope.instances = response;
                        }
                    )
                }
            )
            ;
        }

        $scope.deprovision = function (provisionedResource) {

//            provisionedResource.remove().then(function () {
//                var index = $scope.instances.indexOf(provisionedResource);
//                if (index > -1) $scope.instances.splice(index, 1);
//            });
            provisionedResource.patch({state:'deleting'}).then(function () {
                var index = $scope.instances.indexOf(provisionedResource);
                if (index > -1) $scope.instances[index].state='deleting';
            });
        }

        if (users) {
            $interval(function () {
                var provisionedResources = Restangular.all('provisioned_resources');
                provisionedResources.getList().then(function (response) {
                    $scope.instances = response;
                });
            }, 10000);
        }
    }]);
