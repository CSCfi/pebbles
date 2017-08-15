/* global angular */

'use strict';

var app = angular.module('PBApp', ['ngRoute', 'ngAnimate', 'restangular', 'LocalStorageModule', 'validation.match', 'angularFileUpload', 'schemaForm', 'ui.bootstrap', 'angular-loading-bar', 'angularjs-dropdown-multiselect','ngSanitize']);

app.run(function($location, Restangular, AuthService) {
    Restangular.setFullRequestInterceptor(function(element, operation, route, url, headers) {
        headers.Authorization = 'Basic ' + AuthService.getToken();
        return {
            headers: headers
        };
    });

    Restangular.setErrorInterceptor(function(response) {
        if (response.config.bypassErrorInterceptor) {
            return true;
        } else {
            switch(response.status) {
                case 401:
                    AuthService.logout();
                    $location.path('/');
                    return false;
                case 403:
                    // Pass 403 Forbidden to controllers to handle
                    return true;
                case 404:
                    // Pass 404 Not found to controllers to handle
                    return true;
                case 409:
                    // Pass 409 Conflict to controllers to handle
                    return true;
                case 410:
                    // Pass 410 Gone to controllers to handle
                    return true;
                case 422:
                    // Pass 422 Unprocessable entity to controllers to handle
                    return true;
                default:
                    throw new Error('No handler for status code ' + response.status);
            }
            return false;
        }
    });
});

app.constant('config', {
    partialsDir: '../partials'
});

app.config(function($routeProvider, $compileProvider, RestangularProvider, config) {
    RestangularProvider.setBaseUrl('/api/v1');
    var partialsDir = config.partialsDir;

    $compileProvider.aHrefSanitizationWhitelist(/^\s*(https?|blob):/);

    var redirectIf = function(serviceName, serviceMethod, route) {
        return function($location, $q, $injector) {
            var deferred = $q.defer();
            if ($injector.get(serviceName)[serviceMethod]()) {
                deferred.reject();
                $location.path(route);
            } else {
                deferred.resolve();
            }
            return deferred.promise;
        }
    };

    var notAuthenticatedP = redirectIf('AuthService', 'isNotAuthenticated', '/');
    var alreadyAuthenticatedP = redirectIf('AuthService', 'isAuthenticated', '/dashboard');
    var isAdminP = redirectIf('AuthService', 'isGroupManagerOrAdmin', '/admin-dashboard');
    $routeProvider
        .when('/', {
            templateUrl: partialsDir + '/welcome.html',
            resolve: {
                redirectIfAuthenticated: alreadyAuthenticatedP,
            }
        })
        .when('/dashboard', {
            controller: 'DashboardController',
            templateUrl: partialsDir + '/user_dashboard.html',
            resolve: {
                redirectIfNotAuthenticated: notAuthenticatedP,
                redirectIfAdmin: isAdminP,
                isUserDashboard: function() {return false;},
            }
        })
        .when('/user-dashboard', {
            controller: 'DashboardController',
            templateUrl: partialsDir + '/user_dashboard.html',
            resolve: {
                redirectIfNotAuthenticated: notAuthenticatedP,
                isUserDashboard: function() {return true},
            }
        })
        .when('/admin-dashboard', {
            controller: 'DashboardController',
            templateUrl: partialsDir + '/admin_dashboard.html',
            resolve: {
                redirectIfNotAuthenticated: notAuthenticatedP,
                isUserDashboard: function() {return false},
            }
        })
        .when('/admin-stats', {
            controller: 'StatsController',
            templateUrl: partialsDir + '/admin_stats.html',
            resolve: {
                redirectIfNotAuthenticated: notAuthenticatedP,
            }
        })
        .when('/instance_details/:instance_id', {
            controller: 'InstanceDetailsController',
            templateUrl: partialsDir + '/instance_details.html',
            resolve: {
                redirectIfNotAuthenticated: notAuthenticatedP,
            }
        })
        .when('/users', {
            controller: 'UsersController',
            templateUrl: partialsDir + '/users.html',
            resolve: {
                redirectIfNotAuthenticated: notAuthenticatedP,
            }
        })
        .when('/groups', {
            controller: 'GroupsController',
            templateUrl: partialsDir + '/groups.html',
            resolve: {
                redirectIfNotAuthenticated: notAuthenticatedP,
            }
        })
         .when('/blueprints', {
            controller: 'BlueprintsController',
            templateUrl: partialsDir + '/blueprints.html',
            resolve: {
                redirectIfNotAuthenticated: notAuthenticatedP,
            }
        })
        .when('/configure', {
            controller: 'ConfigureController',
            templateUrl: partialsDir + '/configure.html',
            resolve: {
                redirectIfNotAuthenticated: notAuthenticatedP,
            }
        })
        .when('/account', {
            controller: 'AccountController',
            templateUrl: partialsDir + '/account.html',
            resolve: {
                redirectIfNotAuthenticated: notAuthenticatedP,
            }
        })
        .when('/activate/:token', {
            controller: 'ActivationController',
            templateUrl: partialsDir + '/activation.html',
            resolve: {
                redirectIfAuthenticated: alreadyAuthenticatedP,
            }
        })
        .when('/initialize', {
            controller: 'InitializationController',
            templateUrl: partialsDir + '/initialize.html'
        })
        .when('/reset_password/:token', {
            controller: 'ResetPasswordController',
            templateUrl: partialsDir + '/reset_password.html'
        })
        .when('/registration_success', {
            templateUrl: partialsDir + '/registration_success.html'
        })
        .when('/reset_password', {
            controller: 'ResetPasswordController',
            templateUrl: partialsDir + '/reset_password.html'
        });

});
