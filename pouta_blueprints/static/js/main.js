/* global angular */

'use strict';

var app = angular.module('resourceCloudApp', ['ngRoute', 'restangular', 'LocalStorageModule', 'validation.match', 'angularFileUpload', 'schemaForm']);

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

app.config(function($routeProvider, $compileProvider, RestangularProvider) {
    RestangularProvider.setBaseUrl('/api/v1');
    var partialsDir = '../partials';

    $compileProvider.aHrefSanitizationWhitelist(/^\s*(https?|blob):/);

    var redirectIfAuthenticated = function(route) {
        return function($location, $q, AuthService) {
            var deferred = $q.defer();
            if (AuthService.isAuthenticated()) {
                deferred.reject();
                $location.path(route);
            } else {
                deferred.resolve();
            }
            return deferred.promise;
        };
    };

    var redirectIfNotAuthenticated = function(route) {
        return function($location, $q, AuthService) {
            var deferred = $q.defer();
            if (! AuthService.isAuthenticated()) {
                deferred.reject();
                $location.path(route);
            } else {
                deferred.resolve();
            }
            return deferred.promise;
        };
    };

    $routeProvider
        .when('/', {
            templateUrl: partialsDir + '/welcome.html',
            resolve: {
                redirectIfAuthenticated: redirectIfAuthenticated('/dashboard')
            }
        })
        .when('/dashboard', {
            controller: 'DashboardController',
            templateUrl: partialsDir + '/dashboard.html',
            resolve: {
                redirectIfNotAuthenticated: redirectIfNotAuthenticated('/')
            }
        })
        .when('/instance_details/:instance_id', {
            controller: 'InstanceDetailsController',
            templateUrl: partialsDir + '/instance_details.html',
            resolve: {
                redirectIfNotAuthenticated: redirectIfNotAuthenticated('/')
            }
        })
        .when('/users', {
            controller: 'UsersController',
            templateUrl: partialsDir + '/users.html',
            resolve: {
                redirectIfNotAuthenticated: redirectIfNotAuthenticated('/')
            }
        })
        .when('/configure', {
            controller: 'ConfigureController',
            templateUrl: partialsDir + '/configure.html',
            resolve: {
                redirectIfNotAuthenticated: redirectIfNotAuthenticated('/')
            }
        })
        .when('/account', {
            controller: 'AccountController',
            templateUrl: partialsDir + '/account.html',
            resolve: {
                redirectIfNotAuthenticated: redirectIfNotAuthenticated('/')
            }
        })
        .when('/activate/:token', {
            controller: 'ActivationController',
            templateUrl: partialsDir + '/activation.html',
            resolve: {
                redirectIfAuthenticated: redirectIfAuthenticated('/')
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
        .when('/reset_password', {
            controller: 'ResetPasswordController',
            templateUrl: partialsDir + '/reset_password.html'
        });
});
