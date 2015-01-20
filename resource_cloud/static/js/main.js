'use strict';

var app = angular.module('resourceCloudApp', ['ngRoute', 'restangular', 'LocalStorageModule']);

app.run(function($location, Restangular, AuthService) {
    Restangular.setFullRequestInterceptor(function(element, operation, route, url, headers, params, httpConfig) {
        headers['Authorization'] = 'Basic ' + AuthService.getToken();
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
                    AuthService.logout()
                    $location.path('/session/create');
                    break;
                default:
                    throw new Error('No handler for status code ' + response.status);
            }
            return false;
        }
    });
});

app.config(function($routeProvider, RestangularProvider) {
    RestangularProvider.setBaseUrl('/api/v1');
    var partialsDir = '../partials';

    var redirectIfAuthenticated = function(route) {
        return function($location, $q, AuthService) {
            var deferred = $q.defer();
            if (AuthService.isAuthenticated()) {
                deferred.reject()
                $location.path(route);
            } else {
                deferred.resolve()
            }
            return deferred.promise;
        }
    }

    var redirectIfNotAuthenticated = function(route) {
        return function($location, $q, AuthService) {
            var deferred = $q.defer();
            if (! AuthService.isAuthenticated()) {
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
        .when('/services', {
            controller: 'ServiceController',
            templateUrl: partialsDir + '/services.html',
            resolve: {
                redirectIfAuthenticated: redirectIfAuthenticated('/')
            }
        });
});
