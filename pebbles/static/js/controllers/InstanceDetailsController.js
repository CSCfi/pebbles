app.controller('InstanceDetailsController', ['$q', '$http', '$routeParams', '$scope', '$interval', 'AuthService', 'Restangular',
    function ($q, $http, $routeParams, $scope, $interval, AuthService, Restangular) {

        Restangular.setDefaultHeaders({token: AuthService.getToken()});

        var instance_id = $routeParams.instance_id;
        var instance;

        $scope.new_client_ip='';

        $scope.refresh = function () {
            Restangular.one('instances', instance_id).get().then(function (response) {
                instance = response;
                $scope.instance = response;
            }).then(function () {
                Restangular.one('blueprints', instance.blueprint_id).get().then(function (response) {
                    $scope.blueprint = response;
                });
            }).then(function () {
                $scope.fetchLogs(instance);
            });
        };
        $scope.refresh();

        $scope.fetchLogs = function (instance) {
            if (!instance.logs.length) {
                Restangular.one('instances', instance.id).get().then(function (response) {
                    instance = response;
                    $scope.instance = instance;
                });
            }
        };

        $scope.getLogs = function(instance) {
            var full_log_text = "";
            if (instance) {
                for (var log_index in instance['logs']) {
                    var log = instance['logs'][log_index];
                    var datetime = new Date(log.timestamp * 1000);  // Multiplication for milliseconds
                    full_log_text += "[" + datetime.toLocaleString('en-GB') + "]:" + log.log_level + ":" + log.message;
                }
            }
            return full_log_text;
        }

        $scope.get_my_ip = function () {
            $http(
                {
                    method: "GET",
                    url: '/api/v1/what_is_my_ip',
                    headers: {
                        token: AuthService.getToken(),
                        Authorization: "Basic " + AuthService.getToken()
                    }
                }
            ).success(function (data) {
                    $scope.new_client_ip=data['ip'];
                }
            );
        };

        $scope.update_client_ip = function () {
            instance.client_ip = $scope.new_client_ip;
            instance.put().then(function () {
                $scope.refresh();
            });
        };


        var stop;
        $scope.startPolling = function () {
            if (angular.isDefined(stop)) {
                return;
            }
            stop = $interval(function () {
                if (AuthService.isAuthenticated()) {
                    $scope.refresh();
                } else {
                    $interval.cancel(statePollInterval);
                }
            }, 10000);
        };

        $scope.stopPolling = function () {
            if (angular.isDefined(stop)) {
                $interval.cancel(stop);
                stop = undefined;
            }
        };

        $scope.$on('$destroy', function () {
            $scope.stopPolling();
        });

        $scope.startPolling();
    }
])
;
