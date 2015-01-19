'use strict';

window.ResourceCloud = angular.module('resourceCloudApp', ['ngRoute', 'restangular', 'LocalStorageModule'])

.run(function($location, Restangular, authService) {
    Restangular.setFullRequestInterceptor(function(element, operation, route, url, headers, params, httpConfig) {
        headers['Authorization'] = 'Basic ' + authService.getToken();
        return {
            headers: headers
        };
    });

    Restangular.setErrorInterceptor(function(response, deferred, responseHandler) {
        if (response.config.bypassErrorInterceptor) {
            return true;
        } else {
            switch(response.status) {
                case 401:
                    authService.logout()
                    $location.path('/session/create');
                    break;
                default:
                    throw new Error('No handler for status code ' + response.status);
            }
            return false;
        }
    });
})

.config(function($routeProvider, RestangularProvider) {
    RestangularProvider.setBaseUrl('/api/v1');
    var partialsDir = '../partials';

    var redirectIfAuthenticated = function(route) {
        return function($location, $q, authService) {
            var deferred = $q.defer();
            if (authService.isAuthenticated()) {
                deferred.reject()
                $location.path(route);
            } else {
                deferred.resolve()
            }
            return deferred.promise;
        }
    }

    var redirectIfNotAuthenticated = function(route) {
        return function($location, $q, authService) {
            var deferred = $q.defer();
            if (! authService.isAuthenticated()) {
                deferred.reject()
                $location.path(route);
            } else {
                deferred.resolve()
            }
            return deferred.promise;
        }
    }

    $routeProvider
        .when('/', {
            templateUrl: partialsDir + '/welcome.html'
        })
        .when('/dashboard', {
            controller: 'DashboardController',
            templateUrl: partialsDir + '/dashboard.html',
            resolve: {
                redirectIfNotAuthenticated: redirectIfNotAuthenticated('/')
            }
        })
        .when('/app', {
            controller: 'ApplicationController',
            templateUrl: partialsDir + '/app.html'
        })
        .when('/services', {
            controller: 'ServiceController',
            templateUrl: partialsDir + '/services.html',
            resolve: {
                redirectIfAuthenticated: redirectIfAuthenticated('/')
            }
        });
})
.factory('authService', ['$q', 'localStorageService', 'Session', function($q, localStorageService, Session) {
    return {
        login : function(email, password) {
            var me = this;
            var deferred = $q.defer();
            var credentials = {'email': email, 'password': password};
            Session.create(credentials, true).then(function(response) {
                me.setToken(response.token);
                me.setAdminStatus(response.is_admin);
                return deferred.resolve(response);
            }, function(response) {
                if (response.status == 401) {
                    return deferred.reject(false);
                }
                throw new Error("No handler for status code " + response.status);
            });
            return deferred.promise;
        },

        logout : function() {
            var deferred = $q.defer();
            localStorageService.clearAll();
            return deferred.promise;
        },

        isAuthenticated : function() {
            var token = this.getToken();
            if (token) {
                return true;
            }
            localStorageService.clearAll();
            return false;
        },
        
        isAdmin : function() {
            var adminStatus = this.getAdminStatus();
            if (adminStatus == "true") {
                return true;
            }
            return false;
        },

        setToken : function(token) {
            localStorageService.set('token', btoa(token + ":"));
        },

        getToken : function() {
            return localStorageService.get('token');
        },

        setAdminStatus : function(isAdmin) {
            localStorageService.set('isAdmin', isAdmin);
        },

        getAdminStatus : function() {
            return localStorageService.get('isAdmin');
        }
    }
}])
.factory('Session', function(Restangular) {
    var Session;
    Session = {
        create: function(data, bypassErrorInterceptor) {
            return Restangular
                .one('sessions')
                .withHttpConfig({bypassErrorInterceptor: bypassErrorInterceptor})
                .customPOST(data);
        }
    };
    return Session;
})
.controller('ApplicationController', ['$scope', '$routeParams', '$http', function($scope, $routeParams, $http) {
    
}])
.controller('DashboardController', ['$scope', '$routeParams', 'authService', 'Restangular',
                            function($scope, $routeParams, authService, Restangular) {
    
    Restangular.setDefaultHeaders({token: authService.getToken()});

    if (authService.isAdmin()) {
        var users = Restangular.all('users');
        users.getList().then(function(response) {
            $scope.users = response;
        });

        $scope.new_user = '';
        $scope.add_user = function(email) {
            var user_parameters = { email: email };
            if (email) {
                users.post(user_parameters).then(function(response) {
                    $scope.users.push(response);
                });
            }
        }

        $scope.remove_user = function(user) {
            user.remove().then(function() {
                var index = $scope.users.indexOf(user);
                if (index > -1) $scope.users.splice(index, 1);
            });
        }
    }

    var services = Restangular.all('services');
    services.getList().then(function(response) {
          $scope.services = response;
    });
    
    $scope.call_task = function() {
        services.post({})   
    }
}])
.controller('AuthController', ['$scope', '$location', 'authService', function($scope, $location, authService) {
    $scope.isLoggedIn = function() {
        return authService.isAuthenticated();
    };

    $scope.login = function() {
        authService.login($scope.email, $scope.password).then(function() {
        })
    };

    $scope.logout = function() {
        authService.logout();
        $scope.email = "";
        $scope.password = "";
        $location.path("/");
    };
}]);
