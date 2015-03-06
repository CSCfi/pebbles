app.controller('InstanceDetailsController', ['$q', '$http', '$routeParams', '$scope', '$interval', 'AuthService', 'Restangular',
    function ($q, $http, $routeParams, $scope, $interval, AuthService, Restangular) {

        Restangular.setDefaultHeaders({token: AuthService.getToken()});

        var instance_id = $routeParams.instance_id;
        var instance;

        $scope.refresh = function () {
            Restangular.one('provisioned_resources', instance_id).get().then(function (response) {
                instance = response;
                $scope.instance = response;
            }).then(function () {
                Restangular.one('resources', instance.resource_id).get().then(function (response) {
                    $scope.service = response;
                });
            }).then(function () {
                $scope.fetchLogs(instance);
            });
        };
        $scope.refresh();

        $scope.fetchLogs = function (instance) {
            if (!instance.logs.length) {
                Restangular.one('provisioned_resources', instance.id).get().then(function (response) {
                    instance = response;
                    $scope.instance = instance;
                });
            }
            angular.forEach(instance.logs, function (log) {
                $http(
                    {
                        method: "GET",
                        url: log.url,
                        log_type: log.type,
                        headers: {
                            token: AuthService.getToken(),
                            Authorization: "Basic " + AuthService.getToken()
                        }
                    }
                ).success(function (data, status, headers, config) {
                        var log_type = config.log_type;
                        if (!$scope.logs) {
                            $scope.logs = {};
                        }
                        $scope.logs[log_type] = data;
                    }
                );
            });
        };

        var statePollInterval = $interval(function () {
            if (AuthService.isAuthenticated()) {
                $scope.refresh();
            } else {
                $interval.cancel(statePollInterval);
            }
        }, 10000);
    }
])
;
